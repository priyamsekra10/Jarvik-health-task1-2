from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
import logging
import os
import requests

from .config import get_settings
from .database import get_db_connection, init_db
from .models import (
    AudioProcessingInput,
    AudioProcessingOutput,
    NarrativeInput,
    NarrativeOutput
)
from .auth.models import Token, User
from .auth.utils import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_active_user,
    fake_users_db
)
from .logging_config import setup_logging
from openai import OpenAI
from datetime import datetime
from typing import List
import mysql.connector
from mysql.connector import Error
import json

# Initialize logging
logger = setup_logging()

# Initialize settings
settings = get_settings()

client = OpenAI(api_key=settings.OPENAI_API_KEY)


# FastAPI application
app = FastAPI(title="Jarvic Health API")

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Starting up the application")
    init_db()

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@app.post("/process_audio/", response_model=AudioProcessingOutput)
async def process_audio(
    input: AudioProcessingInput,
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"User {current_user.username} processing audio request for chat_id: {input.chat_id}")    
    # Fallback audio file if link is invalid
    default_audio_path = "/app/audio.mp3"
    temp_audio_path = "/tmp/downloaded_audio.mp3"
    audio_file_to_use = default_audio_path

    try:
        # Attempt to download audio file
        try:
            logger.info(f"Attempting to download audio from: {input.audio_link}")
            response = requests.get(input.audio_link, stream=True, timeout=10)
            response.raise_for_status()
            
            # Save downloaded audio to temporary location
            with open(temp_audio_path, "wb") as f:
                f.write(response.content)
            audio_file_to_use = temp_audio_path
            logger.info("Audio file downloaded successfully")
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to download audio: {str(e)}")
            if os.path.exists(default_audio_path):
                logger.info("Using default audio.mp3 as fallback :", default_audio_path)
                audio_file_to_use = default_audio_path
            else:
                logger.error("Default audio file not found", default_audio_path)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Both download and fallback audio file unavailable"
                )

        # Transcribe audio file
        try:
            logger.info(f"Starting audio transcription using file: {audio_file_to_use}")
            with open(audio_file_to_use, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            transcript_text = transcription.text
            logger.info("Audio transcription completed successfully")
        except Exception as e:
            logger.error("Error during transcription", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Transcription failed: {str(e)}"
            )

        # Generate summary
        try:
            logger.info("Generating summary using GPT-4")
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", 
                    "content": f"""
                    You are an assistant specialized in analyzing audio transcriptions from nurses and generating concise, well-structured patient health reports.
                    Input:
                    You will receive a transcription summarizing the patient’s current health status.

                    Expected Output:
                    1. A clear and organized summary of the patient’s health report, emphasizing key details.
                    2. Use natural language, ensuring all important details are included.
                    3. Do not assume any information that is not explicitly provided in the transcription.
                    4. Do not use any symbols like \n\n(slash n), **, etc. Just normal paragraph. Directly start with the summary. Do not use anything like "Summary:" or "Patient's Health Report:".
                    Transcription Provided:
                    {transcript_text}

                    Example Output:
                    The patient, Jane Smith, aged 54, was admitted on December 10th for severe headaches and dizziness. Initial vitals included a blood pressure of 140/90 and a heart rate of 85 bpm. A CT scan indicated mild cerebral edema. By December 11th, the headache intensity had reduced, though dizziness persisted. Continued NSAID treatment and physical therapy were recommended. Discharge is tentatively planned for December 15th, pending results.
                    """},
                ]
            )
            summary = completion.choices[0].message.content
            logger.info("Summary generation completed")
        except Exception as e:
            logger.error("Error generating summary", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Summary generation failed: {str(e)}"
            )

        # Prepare output
        process_id = f"{input.chat_id}{input.user_id}"[-5:]
        output = AudioProcessingOutput(
            process_id=process_id,
            audio_link=input.audio_link if audio_file_to_use != default_audio_path else "default_audio",
            audio_text=transcript_text,
            text_summary=summary,
            processed_at=datetime.utcnow().isoformat() + "Z",
            status="completed"
        )

        # Save to database
        try:
            logger.info(f"Saving audio processing record to database for process_id: {process_id}")
            conn = get_db_connection()
            with conn.cursor() as cursor:
                insert_query = """
                INSERT INTO audio_processing_records 
                (process_id, chat_id, user_id, audio_link, audio_text, text_summary, processed_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    output.process_id,
                    input.chat_id,
                    input.user_id,
                    output.audio_link,
                    output.audio_text,
                    output.text_summary,
                    datetime.utcnow(),
                    output.status
                ))
                conn.commit()
            
            logger.info("Database record saved successfully")
            return output
            
        except Error as e:
            logger.error(f"Database error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )
    finally:
        # Clean up downloaded audio file if it exists
        if os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
                logger.info("Cleaned up temporary audio file")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary audio file: {str(e)}")

@app.post("/combine_narrative/", response_model=NarrativeOutput)
async def combine_narrative(
    input: NarrativeInput,
    current_user: User = Depends(get_current_active_user)
):
    logger.info(f"User {current_user.username} processing narrative request for visit_id: {input.visit_id}")    
    try:
        # Join entries
        combined_input = "\n\n".join(input.entries)
        logger.debug(f"Combined input entries: {combined_input[:200]}...")  # Log first 200 chars

        # Generate narrative using GPT-4
        try:
            logger.info("Generating narrative using GPT-4")
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", 
                    "content": """
                    You are a nurse creating a comprehensive narrative for a patient's health record.
                    Input: You will receive multiple entries summarizing the patient's health at different times.
                    Expected Output:
                    1. Combine all entries into a single cohesive narrative.
                    2. Use natural language and proper formatting to ensure clarity and flow.
                    3. Ensure details are structured in chronological order, and avoid redundancies.
                    4. Do not assume any information that is not explicitly provided in the entries.
                    5. Do not use any symbols like \n\n(slash n), **, etc. Just normal paragraph.
                    6. Try to keep the structure similar to the exmaple below:
                    
                    07:00 Skilled nurse arrives at home and receives patient from outgoing nurse who stated that patient had a good day start of shift vital signs 07:00 Skilled nurse arrives at home and receives patient from outgoing nurse who stated that patient had a good day start of shift vital signs checked and documented, family and Patient covid assessment was done according to CDC guidelines, Pt and SN temp. monitored and checked and documented, family and Patient covid assessment was done according to CDC guidelines, Pt and SN temp. monitored and recorded, all within normal limit, Pt head to toe assessment done, pt remains stable, lungs sounds present and clear. At 14:05, Pt had a large sized soft stool and was well cleaned, incontinent care done and new diaper worn. At 15:00 due medication AFOS 4 to 14:05, Pt had a large sized soft stool and was well cleaned, incontinent care done and new diaper worn. At 15:00 due medication AFOS 4 to 8 hrs as tolerated, Pt continue feeding, will continue monitoring. At 15:00 Pt vital signs checked and recorded, Pt continues feeding, will 8 hrs as tolerated, Pt continue feeding, will continue monitoring. At 15:00 Pt vital signs checked and recorded, Pt continues feeding, will continue monitoring, Pt repositioned every 2hrs to prevent skin irritations and to maintain skin integrity. No new concern at this time, pt remains stable, End of shift report given to incoming Trash emptied, emergency equipments at pt bedside. No new concern at this time, pt remains stable, End of shift report given to incoming nurse, Nurse off the clock.
                    """
                    },
                    {"role": "user", "content": combined_input},
                ]
            )
            narrative = completion.choices[0].message.content
            logger.info("Narrative generation completed")
            logger.debug(f"Generated narrative: {narrative[:200]}...")  # Log first 200 chars
        except Exception as e:
            logger.error("Error generating narrative", exc_info=True)
            raise HTTPException(status_code=500, detail="Narrative generation failed")

        # Prepare output
        output = NarrativeOutput(
            visit_id=input.visit_id,
            chat_id=input.chat_id,
            user_id=input.user_id,
            narrative=narrative,
            status="success"
        )

        # Save to database
        try:
            logger.info(f"Saving narrative record to database for visit_id: {input.visit_id}")
            conn = get_db_connection()
            cursor = conn.cursor()
            
            insert_query = """
            INSERT INTO narrative_records 
            (visit_id, chat_id, user_id, narrative, status)
            VALUES (%s, %s, %s, %s, %s)
            """
            
            cursor.execute(insert_query, (
                output.visit_id,
                output.chat_id,
                output.user_id,
                output.narrative,
                output.status
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            logger.info("Database record saved successfully")
            
        except Error as e:
            logger.error(f"Database error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Database error")

        logger.info(f"Narrative combination completed successfully for visit_id: {input.visit_id}")
        return output

    except Exception as e:
        logger.error(f"Unexpected error in combine_narrative: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception handler caught: {str(exc)}", exc_info=True)
    return {"detail": str(exc)}


# change api key
# audio link sahi karna hai

