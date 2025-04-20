import streamlit as st
from supabase import create_client, Client
from PIL import Image
import requests
from io import BytesIO
import google.generativeai as genai
import pandas as pd
import json
import re

# --- Supabase Config ---
SUPABASE_URL = "https://qorkvjajwksrckvomjqj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFvcmt2amFqd2tzcmNrdm9tanFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUwNzQzMzUsImV4cCI6MjA2MDY1MDMzNX0.D5wkYGKLCP2LIQlwO8_lD5drHcuIol4QOlW8qPtz0vE"
SUPABASE_BUCKET = "reciepts"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Gemini Config ---
GOOGLE_API_KEY = "AIzaSyBfEACHY99TLkwX9wjKzb-TGhLsECfhpGc"
genai.configure(api_key=GOOGLE_API_KEY)

# --- Prepare image for Gemini ---
def prepare_image_for_gemini(image_bytes, mime_type="image/png"):
    return {
        "mime_type": mime_type,
        "data": image_bytes
    }

# --- Gemini image OCR function ---
def get_gemini_response(prompt, image):
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content([prompt, image])
    return response.text

# --- Fetch all data from Supabase tables ---
def fetch_all_table_data():
    try:
        # Fetch employees data
        employees_data = supabase.from_("employees").select("*").execute().data
        
        # Fetch refund_requests data
        refund_requests_data = supabase.from_("refund_requests").select("*").execute().data
        
        return {
            "employees": employees_data,
            "refund_requests": refund_requests_data
        }
    except Exception as e:
        st.error(f"Error fetching table data: {e}")
        return None

# --- Update refund request with amount ---
def update_refund_request_amount(image_url, amount):
    try:
        # Extract ID from filename (handling cases like 'refund_req1?.png')
        file_name = image_url.split('/')[-1]
        
        # Clean the filename - remove ? and anything after it
        clean_name = file_name.split('?')[0]
        
        # Extract numeric ID
        record_id = int(clean_name.replace("refund_req", "").replace(".png", ""))
        
        # Update by ID
        update_response = supabase.from_("refund_requests").update(
            {"amount": float(amount)}
        ).eq("id", record_id).execute()
        
        if len(update_response.data) > 0:
            st.success(f"✅ Updated amount to ${amount} for Receipt ID {record_id}")
            return True
        else:
            st.error(f"❌ No record found with ID {record_id}")
            return False
            
    except Exception as e:
        st.error(f"Error processing receipt: {str(e)}")
        st.error(f"Debug info - File name: {file_name}, Clean name: {clean_name}")
        return False

# --- Insert new employee record ---
def insert_employee_record(name, salary):
    try:
        # Insert new record without specifying ID
        insert_response = supabase.from_("employees").insert({
            "name": name,
            "salary": float(salary)
        }).execute()
        
        if len(insert_response.data) > 0:
            st.success(f"✅ Successfully added new employee: {name} with salary ${salary}")
            return True
        else:
            st.error("❌ Failed to insert new employee record")
            return False
    except Exception as e:
        st.error(f"Error inserting employee record: {str(e)}")
        return False

def update_employee_age(employee_id, age):
    try:
        update_response = supabase.from_("employees").update(
            {"age": int(age)}
        ).eq("id", int(employee_id)).execute()
        
        if len(update_response.data) > 0:
            st.success(f"✅ Updated age to {age} for Employee ID {employee_id}")
            return True
        else:
            st.error(f"❌ No employee found with ID {employee_id}")
            return False
    except Exception as e:
        st.error(f"Error updating employee age: {str(e)}")
        return False

def is_age_update_request(user_prompt):
    # Pattern for "insert the age of id 5, 45"
    pattern = r"(?:insert|update|set)\s+(?:the\s+)?age\s+(?:of|for)\s+id\s+(\d+)\s*,\s*(\d+)"
    match = re.search(pattern, user_prompt, re.IGNORECASE)
    return match

def process_age_update_request(user_prompt):
    match = is_age_update_request(user_prompt)
    if match:
        employee_id = match.group(1).strip()
        age = match.group(2).strip()
        return update_employee_age(employee_id, age)
    return False
# --- Check if user wants to insert data ---
def is_insert_request(user_prompt):
    # More precise pattern that captures just the name after "the name"
    pattern = r"(?:insert|add)\s+(?:a\s+)?row\s+(?:to|in)\s+employees\s+(?:with\s+the\s+name\s+|name\s+)([^,]+?)\s*,\s*salary\s+(\d+)"
    match = re.search(pattern, user_prompt, re.IGNORECASE)
    return match

def process_insert_request(user_prompt):
    match = is_insert_request(user_prompt)  # This defines the 'match' variable
    if match:
        # Clean the name by removing any remaining "the name" text
        name = match.group(1).replace("the name", "").strip()
        salary = match.group(2).strip()
        success = insert_employee_record(name, salary)
        if success:
            st.success(f"✅ Successfully added employee: {name} with salary ${salary}")
            return True
    return False


def delete_employee_by_id(employee_id):
    try:
        delete_response = supabase.from_("employees").delete().eq("id", int(employee_id)).execute()
        
        if len(delete_response.data) > 0:
            st.success(f"✅ Successfully deleted employee with ID {employee_id}")
            return True
        else:
            st.error(f"❌ No employee found with ID {employee_id}")
            return False
    except Exception as e:
        st.error(f"Error deleting employee: {str(e)}")
        return False
    
def is_delete_request(user_prompt):
    # Pattern for "delete the row with id 3"
    pattern = r"delete\s+(?:the\s+)?row\s+(?:with\s+)?id\s+(\d+)"
    match = re.search(pattern, user_prompt, re.IGNORECASE)
    return match
# --- Gemini natural language query response ---
def get_natural_language_response(user_prompt, table_data):
    # First check if this is an insert request
    if is_insert_request(user_prompt):
        process_insert_request(user_prompt)
        return "Employee record has been inserted successfully."
    
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    system_prompt = f"""
You are a helpful assistant that answers questions about the company database.
Here is the current data in our tables:

EMPLOYEES TABLE DATA:
{json.dumps(table_data['employees'], indent=2)}

REFUND_REQUESTS TABLE DATA:
{json.dumps(table_data['refund_requests'], indent=2)}

Based on this data, answer the user's query and show the data in tabular form without anything else 
"""
    
    response = model.generate_content([system_prompt, user_prompt])
    return response.text.strip()

# --- Streamlit UI ---
st.set_page_config(page_title="🧠 AI-Powered Supabase OCR & SQL")
st.title("🧾 Supabase Receipt OCR + 💬 Natural Language Query")

# --- OCR from receipt image ---
st.header("🔍 OCR From Receipt Image")
file_name = st.text_input("Enter receipt file name (e.g., `refund_req1.png`)")

if st.button("Fetch & Analyze Image"):
    if file_name:
        # Remove any double slashes in the path
        clean_file_name = file_name.replace("//", "/")
        public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(clean_file_name)
        
        if public_url:
            st.image(public_url, caption="Fetched Image from Supabase", use_column_width=True)
            st.code(public_url)

            response = requests.get(public_url)
            if response.status_code == 200:
                image_bytes = response.content
                input_prompt = """
You are an expert OCR model. Calculate the total amount and return ONLY the numeric value without any currency symbols or additional text.
For example, if the receipt shows "$15.99", return "15.99".
                """
                gemini_image = prepare_image_for_gemini(image_bytes)
                gemini_response = get_gemini_response(input_prompt, gemini_image)

                st.subheader("📄 Extracted Amount")
                st.text(gemini_response)
                
                # Store the amount and image URL for the update button
                st.session_state.extracted_amount = gemini_response.strip()
                st.session_state.image_url = public_url
            else:
                st.error("Failed to download image.")
        else:
            st.error("Could not generate public URL.")

# Add button to update the refund request if we have an extracted amount
if 'extracted_amount' in st.session_state and 'image_url' in st.session_state:
    if st.button("📤 Upload Amount to Refund Request"):
        try:
            # Convert amount to float
            amount = float(st.session_state.extracted_amount)
            success = update_refund_request_amount(st.session_state.image_url, amount)
            if success:
                # Refresh the page to show updates
                st.rerun()
        except ValueError:
            st.error("❌ The extracted amount is not a valid number. Please check the OCR result.")

# --- Natural Language Query ---
st.header("💬 Ask Your Database")

user_prompt = st.text_input("Type your question (e.g., 'Who are our highest paid employees?' or 'insert a row in employees with the name John doe, salary 30000')")

if st.button("Get Answer"):
    if user_prompt:
        with st.spinner("Processing your request..."):

            delete_match = is_delete_request(user_prompt)
            if delete_match:
                employee_id = delete_match.group(1).strip()
                if delete_employee_by_id(employee_id):
                    st.rerun()
                else:
                    st.error("Failed to delete employee")
            # First check for age updates
            age_match = is_age_update_request(user_prompt)
            if age_match:
                employee_id = age_match.group(1).strip()
                age = age_match.group(2).strip()
                if update_employee_age(employee_id, age):
                    st.rerun()
            
            # Then check for employee inserts
            else:
                insert_match = is_insert_request(user_prompt)  # Renamed to avoid confusion
                if insert_match:
                    if process_insert_request(user_prompt):
                        st.rerun()
                
                # Finally handle normal queries
                else:
                    table_data = fetch_all_table_data()
                    if table_data:
                        response = get_natural_language_response(user_prompt, table_data)
                        st.subheader("🤖 AI Response")
                        st.markdown(response)
