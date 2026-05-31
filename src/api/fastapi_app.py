from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import io
import os
import logging

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Invest AI - Sandbox API",
    description="Backend API for the Simulated Scenario Sandbox.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DISCLAIMER = (
    "This is a theoretical data simulation. Invest AI will analyze this model. "
    "This is not financial advice for your personal assets."
)


def _parse_positions(df: pd.DataFrame) -> list[dict]:
    if "Symbol" not in df.columns:
        raise HTTPException(status_code=400, detail="Missing required column 'Symbol'.")

    positions = []
    for _, row in df.iterrows():
        sym = str(row["Symbol"]).strip().upper()
        if not sym or sym == "NAN":
            continue
        positions.append(
            {
                "symbol": sym,
                "shares": float(row.get("Shares", 0) or 0),
                "cost_basis": float(row.get("CostBasis", row.get("Cost Basis", 0)) or 0),
            }
        )
    if not positions:
        raise HTTPException(status_code=400, detail="No valid symbols found in file.")
    return positions


@app.get("/health")
async def health_check():
    payload = {"status": "healthy", "database": "not_configured"}
    if os.environ.get("DATABASE_URL"):
        try:
            from src.api.sandbox_persistence import get_or_create_sandbox_user

            await get_or_create_sandbox_user()
            payload["database"] = "connected"
        except Exception as exc:
            logger.warning("Database health check failed: %s", exc)
            payload["database"] = "error"
            payload["database_error"] = str(exc)
    return payload


@app.post("/api/sandbox/import")
async def import_sandbox_csv(file: UploadFile = File(...)):
    """
    Import a CSV/Excel file for a simulated scenario.

    Expected columns: Symbol, Shares, CostBasis

    When DATABASE_URL is set, positions are persisted to Postgres under the
    user's "Simulated Scenario" portfolio and returned with weight % on a $100k baseline.
    """
    filename = file.filename or ""
    if not filename.lower().endswith((".csv", ".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only CSV or Excel files are allowed.")

    try:
        contents = await file.read()
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))

        raw_positions = _parse_positions(df)

        if not os.environ.get("DATABASE_URL"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "DATABASE_URL is not configured. "
                    "Run scripts/provision_local_postgres.ps1 or set Azure Postgres in .env."
                ),
            )

        from src.api.sandbox_persistence import persist_sandbox_positions

        saved = await persist_sandbox_positions(raw_positions)

        return {
            "message": "Sandbox scenario successfully loaded.",
            "disclaimer": DISCLAIMER,
            "theoretical_baseline": saved["theoretical_baseline"],
            "positions": saved["positions"],
            "persisted": True,
            "user_slug": saved["user_slug"],
            "portfolio_id": saved["portfolio_id"],
            "portfolio_name": saved["portfolio_name"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Sandbox import failed")
        raise HTTPException(status_code=500, detail=f"Error processing sandbox import: {e}") from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.fastapi_app:app", host="0.0.0.0", port=8000, reload=True)
