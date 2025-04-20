import streamlit as st
from supabase import create_client, Client
from PIL import Image
import requests
from io import BytesIO
import google.generativeai as genai
import pandas as pd
import json

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
# --- Update or create refund request with amount ---
# --- Update refund request amount ---
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
# --- Gemini natural language query response ---
def get_natural_language_response(user_prompt, table_data):
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

user_prompt = st.text_input("Type your question (e.g., 'Who are our highest paid employees?')")

if st.button("Get Answer"):
    if user_prompt:
        with st.spinner("Fetching data and generating response..."):
            # First fetch all table data
            table_data = fetch_all_table_data()
            
            if table_data:
                # Get natural language response from Gemini
                response = get_natural_language_response(user_prompt, table_data)
                
                st.subheader("🤖 AI Response")
                st.markdown(response)