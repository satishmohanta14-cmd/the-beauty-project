"""
Affiliate Outbound Redirection & Click Telemetry Endpoint.
GET /go/{offer_id} -> 307 Temporary Redirect
"""
from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.click_telemetry import ClickTelemetry
from app.models.offer import Offer

router = APIRouter(tags=["Affiliate Redirection"])


@router.get("/go/{offer_id}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def affiliate_redirect(
    offer_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Affiliate redirection link:
    1. Resolves the retailer affiliate tracking deep-link from the `offer` record.
    2. Records click telemetry asynchronously (referrer, user-agent, hashed IP).
    3. Issues a 307 Temporary Redirect to the destination retailer.
    """
    stmt = select(Offer).where(Offer.id == offer_id).limit(1)
    offer = (await db.execute(stmt)).scalar_one_or_none()
    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Offer '{offer_id}' not found",
        )

    # Telemetry data collection
    referrer = request.headers.get("referer")
    user_agent = request.headers.get("user-agent")
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:32]

    telemetry = ClickTelemetry(
        offer_id=offer.id,
        referrer=referrer,
        user_agent=user_agent,
        ip_hash=ip_hash,
    )
    db.add(telemetry)
    await db.commit()

    response = RedirectResponse(
        url=offer.affiliate_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
