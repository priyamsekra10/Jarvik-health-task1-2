from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class AudioProcessingInput(BaseModel):
    audio_link: str
    created_at: Optional[str] = None  # Made optional with default None
    chat_id: str
    user_id: str

class AudioProcessingOutput(BaseModel):
    process_id: str
    audio_link: str
    audio_text: str
    text_summary: str
    processed_at: str
    status: str

class NarrativeInput(BaseModel):
    visit_id: str
    chat_id: str
    user_id: str
    entries: List[str]

class NarrativeOutput(BaseModel):
    visit_id: str
    chat_id: str
    user_id: str
    narrative: str
    status: str