import streamlit as st
import supabase
import requests
import torch
from pydub import AudioSegment
from pydub.effects import normalize, compress_dynamic_range
import tempfile
import os
import numpy as np
from scipy import signal
from transformers import pipeline
import google.generativeai as genai

# Initialize Supabase client with direct credentials
def init_supabase():
    SUPABASE_URL = "https://qorkvjajwksrckvomjqj.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFvcmt2amFqd2tzcmNrdm9tanFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUwNzQzMzUsImV4cCI6MjA2MDY1MDMzNX0.D5wkYGKLCP2LIQlwO8_lD5drHcuIol4QOlW8qPtz0vE"
    return supabase.create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Gemini
def init_gemini():
    GOOGLE_API_KEY = "AIzaSyBfEACHY99TLkwX9wjKzb-TGhLsECfhpGc"
    genai.configure(api_key=GOOGLE_API_KEY)

# Download audio file from URL
def download_audio(audio_url):
    try:
        response = requests.get(audio_url)
        response.raise_for_status()
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            tmp_file.write(response.content)
            return tmp_file.name
    except Exception as e:
        st.error(f"Error downloading audio: {e}")
        return None

def enhance_audio(audio_path):
    try:
        # Load audio file
        audio = AudioSegment.from_file(audio_path)
        
        # Convert to mono if stereo
        if audio.channels > 1:
            audio = audio.set_channels(1)
            
        # Set consistent frame rate (16kHz is good for speech)
        audio = audio.set_frame_rate(16000)
        
        # Boost volume by 10dB (adjust based on your needs)
        audio = audio + 10
        
        # Normalize audio to -3dBFS peak
        audio = normalize(audio, headroom=3.0)
        
        # Apply dynamic range compression to make quiet parts more audible
        audio = compress_dynamic_range(audio, threshold=-20.0, ratio=4.0)
        
        # Get samples as numpy array and ensure proper format
        samples = np.array(audio.get_array_of_samples())
        sample_rate = audio.frame_rate
        
        # Make sure the array is C-contiguous
        if not samples.flags['C_CONTIGUOUS']:
            samples = np.ascontiguousarray(samples)
        
        # Design bandpass filter (300Hz-4000Hz)
        nyquist = 0.5 * sample_rate
        low = 300 / nyquist
        high = 4000 / nyquist
        b, a = signal.butter(5, [low, high], btype='band')
        
        # Apply filter with proper data type conversion
        filtered_samples = signal.filtfilt(b, a, samples.astype(np.float32))
        
        # Convert back to original dtype and ensure no clipping
        filtered_samples = np.clip(filtered_samples, -2**15, 2**15-1).astype(np.int16)
        
        # Convert back to AudioSegment
        enhanced_audio = audio._spawn(filtered_samples)
        
        # Create temporary file for enhanced audio
        temp_enhanced_path = audio_path.replace(".mp3", "_enhanced.wav")
        enhanced_audio.export(temp_enhanced_path, format="wav")
        
        return temp_enhanced_path
    except Exception as e:
        st.error(f"Error enhancing audio: {e}")
        return audio_path  # Fallback to original if enhancement fails

# Transcribe audio using local Whisper model with Urdu language specified
def transcribe_audio(audio_path):
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        pipe = pipeline(
            "automatic-speech-recognition",
            model="openai/whisper-base",
            device=device
        )
        
        # Enhance audio quality before transcription
        enhanced_audio_path = enhance_audio(audio_path)
        
        # Transcribe with Urdu language specified
        result = pipe(
            enhanced_audio_path,
            generate_kwargs={"language": "urdu"},
            return_timestamps=True
        )
        
        # Clean up temporary files
        if enhanced_audio_path != audio_path:  # Only delete if we created an enhanced version
            os.unlink(enhanced_audio_path)
        
        return result["text"]
    except Exception as e:
        st.error(f"Error transcribing audio: {e}")
        return None

# Update transcription and summary in Supabase
def update_transcription_and_summary(supabase_client, record_id, transcription, summary):
    try:
        response = supabase_client.table("refund_requests").update({
            "transcription": transcription,
            "transcription_summary": summary
        }).eq("id", record_id).execute()
        
        if len(response.data) > 0:
            return True
        return False
    except Exception as e:
        st.error(f"Error updating transcription and summary: {e}")
        return False

# Summarize text using Gemini with improved prompt for low-quality transcripts
def summarize_text(text):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""
Please analyze the following Urdu audio transcription carefully. 
The audio quality was poor, so some words may be unclear or incorrect.
Focus on extracting the main intent and key details.

Guidelines:
1. Identify the speaker's primary request or concern
2. Note any important names, numbers, or dates mentioned
3. Ignore unclear or garbled words
4. Provide a concise English summary (1-2 sentences)

Urdu Transcript:
{text}

English Summary:
"""
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Error summarizing text: {e}")
        return None

# Main Streamlit app
def main():
    st.title("Enhanced Urdu Audio Transcription")
    st.markdown("""
    This version includes audio enhancement to improve transcription quality for low-volume/poor-quality recordings.
    """)
    
    # Initialize clients
    supabase_client = init_supabase()
    init_gemini()
    
    # Check for CUDA availability
    if torch.cuda.is_available():
        st.success("GPU acceleration available (CUDA)")
    else:
        st.warning("Using CPU - transcription will be slower")
    
    # Fetch records with audio URLs but no transcriptions
    try:
        response = supabase_client.table("refund_requests").select("*").execute()
        records = [dict(record) for record in response.data 
                  if record.get("audio_url", "").endswith(".mp3?") 
                  and (not record.get("transcription") or not record.get("transcription_summary"))]
        
        if not records:
            st.info("No records with MP3 audio URLs needing transcription found.")
            return
            
        st.write(f"Found {len(records)} records needing transcription")
        
        for record in records:
            with st.expander(f"Record ID: {record.get('id')}"):
                audio_url = record.get("audio_url")
                st.write(f"Audio URL: {audio_url}")
                
                # Display audio player with volume boost
                audio_html = f"""
                <audio controls style="width: 100%">
                    <source src="{audio_url}" type="audio/mp3">
                    Your browser does not support the audio element.
                </audio>
                <p><small>Note: Original audio - processing will enhance volume/clarity</small></p>
                """
                st.markdown(audio_html, unsafe_allow_html=True)
                
                if st.button(f"Transcribe & Summarize Record {record.get('id')}", 
                           key=f"process_{record.get('id')}"):
                    with st.spinner("Processing audio (enhancing quality first)..."):
                        # Download audio
                        audio_path = download_audio(audio_url)
                        
                        if audio_path:
                            # Transcribe
                            transcription = transcribe_audio(audio_path)
                            
                            if transcription:
                                # Store in session state
                                st.session_state[f"transcription_{record.get('id')}"] = transcription
                                
                                # Generate summary
                                summary = summarize_text(transcription)
                                if summary:
                                    st.session_state[f"summary_{record.get('id')}"] = summary
                                
                                # Clean up
                                os.unlink(audio_path)
                            else:
                                st.error("Transcription failed")
                
                # Display transcription if available
                if f"transcription_{record.get('id')}" in st.session_state:
                    st.subheader("Enhanced Transcription (Urdu)")
                    st.text_area("Transcription", 
                               st.session_state[f"transcription_{record.get('id')}"], 
                               height=200, 
                               key=f"display_transcription_{record.get('id')}")
                
                # Display summary if available
                if f"summary_{record.get('id')}" in st.session_state:
                    st.subheader("English Summary")
                    st.info(st.session_state[f"summary_{record.get('id')}"])
                
                # Save button
                if (f"transcription_{record.get('id')}" in st.session_state and 
                    f"summary_{record.get('id')}" in st.session_state):
                    if st.button(f"Save to Database", key=f"save_{record.get('id')}"):
                        with st.spinner("Saving to database..."):
                            success = update_transcription_and_summary(
                                supabase_client,
                                record.get("id"),
                                st.session_state[f"transcription_{record.get('id')}"],
                                st.session_state[f"summary_{record.get('id')}"]
                            )
                            if success:
                                st.success("Successfully saved enhanced transcription and summary!")
                                st.rerun()
                            else:
                                st.error("Failed to save to database")
                
    except Exception as e:
        st.error(f"Error fetching records: {e}")

if __name__ == "__main__":
    main()
