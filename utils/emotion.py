import datetime

def calculate_circadian_rhythm(current_hour: int) -> dict:
    """Returns energy modifier and circadian mood description based on hour."""
    if 0 <= current_hour < 6:
        return {"energy_mod": 0.4, "circadian_mood": "Sleepy, terse, late-night vibe"}
    elif 6 <= current_hour < 12:
        return {"energy_mod": 1.0, "circadian_mood": "Fresh, energetic, morning enthusiasm"}
    elif 12 <= current_hour < 18:
        return {"energy_mod": 0.9, "circadian_mood": "Focused, professional, afternoon clarity"}
    else:
        return {"energy_mod": 0.7, "circadian_mood": "Relaxed, reflective, evening chill"}

def compute_digital_entity_state(affinity_score: float, local_timezone_offset: int = 7) -> dict:
    """
    Computes final Mood and Energy Level based on Affinity Score and Circadian Rhythm.
    affinity_score: 0.0 (Hates) to 1.0 (Loves), default 0.5.
    """
    # 1. Base emotion from affinity
    if affinity_score <= 0.3:
        base_mood = "PROTECTIVE"
        base_energy = 0.5
    elif affinity_score >= 0.7:
        base_mood = "OPTIMISTIC"
        base_energy = 1.0
    else:
        base_mood = "NEUTRAL"
        base_energy = 0.8
        
    # 2. Time of day
    now = datetime.datetime.utcnow()
    local_time = now + datetime.timedelta(hours=local_timezone_offset)
    current_hour = local_time.hour
    
    circadian = calculate_circadian_rhythm(current_hour)
    
    # 3. Blending
    final_energy = min(1.0, base_energy * circadian["energy_mod"])
    final_mood = f"{base_mood}. Note on your current state: {circadian['circadian_mood']} ({local_time.strftime('%H:%M local time')})."
    
    return {
        "mood": final_mood,
        "energy_level": round(final_energy, 2),
        "user_affinity": affinity_score
    }
