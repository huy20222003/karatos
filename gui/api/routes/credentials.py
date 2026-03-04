"""
Credentials API Routes — Secure VAULT management for agent service tokens.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class CredentialCreate(BaseModel):
    name: str
    service: str
    token: str
    notes: Optional[str] = ""


@router.get("")
async def list_credentials():
    """List all stored credentials (names and services only — never tokens)."""
    try:
        from tools.credential_manager import CredentialManager
        creds = CredentialManager.list_credentials()
        return {"credentials": creds}
    except Exception as e:
        return {"credentials": [], "error": str(e)}


@router.post("")
async def store_credential(body: CredentialCreate):
    """Encrypt and store a new credential in the VAULT."""
    if not body.name or not body.token:
        raise HTTPException(400, "Name and token are required")

    try:
        from tools.credential_manager import CredentialManager
        result = CredentialManager.store_credential(
            name=body.name,
            service=body.service,
            token=body.token,
            notes=body.notes,
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to store credential: {str(e)}")


@router.delete("/{name}")
async def revoke_credential(name: str):
    """Delete a credential from the VAULT."""
    try:
        from tools.credential_manager import CredentialManager
        result = CredentialManager.revoke_credential(name)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to revoke credential: {str(e)}")
