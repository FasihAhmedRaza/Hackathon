# AI-Powered Supabase OCR & Urdu Audio Transcription

This project is a Streamlit-based web application that integrates AI-powered tools for processing receipts and transcribing Urdu audio. It leverages Supabase for database and storage management, Google Gemini for generative AI capabilities, and OpenAI Whisper for speech recognition.


## Features

### 1. Receipt OCR and Amount Extraction
- Upload receipt images stored in Supabase.
- Use Google Gemini's OCR capabilities to extract the total amount from the receipt.
- Update the extracted amount in the Supabase database.

### 2. Urdu Audio Transcription and Summarization
- Download and enhance audio files for better transcription quality.
- Transcribe Urdu audio using OpenAI Whisper.
- Summarize the transcription into concise English text using Google Gemini.

### 3. Natural Language Query
- Query the database using natural language.
- Get AI-generated responses based on the data in the `employees` and `refund_requests` tables.
