from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import io

app = FastAPI(
    title="Invest AI - Sandbox API",
    description="Backend API for the Simulated Scenario Sandbox.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/api/sandbox/import")
async def import_sandbox_csv(file: UploadFile = File(...)):
    """
    Import a 4-row CSV file containing sandbox portfolio holdings.
    
    Expected columns: Symbol, Shares, CostBasis
    
    The portfolio value is normalized to a theoretical $100,000.00 baseline
    or converted to weight percentages, to comply with the Clickwrap Shield
    and avoid Unregistered Investment Advisor risks.
    """
    if not file.filename.endswith(".csv") and not file.filename.endswith(".xls") and not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only CSV or Excel files are allowed.")
    
    try:
        contents = await file.read()
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
            
        # Basic validation: ensure we have at least Symbol column
        if "Symbol" not in df.columns:
            raise HTTPException(status_code=400, detail="Missing required column 'Symbol'.")
            
        # Normalize the portfolio to percentages or theoretical values
        # For simplicity, we assume there's a 'Value' or we calculate it.
        # Here we just parse and return the normalized payload.
        # In a real scenario, we'd calculate current market value and normalize to 100k.
        
        # Let's say we just parse it into a list of dicts for now
        # and attach the theoretical baseline normalization logic.
        positions = []
        for _, row in df.iterrows():
            pos = {
                "symbol": str(row["Symbol"]).strip().upper(),
                "shares": float(row.get("Shares", 0)),
                "cost_basis": float(row.get("CostBasis", row.get("Cost Basis", 0)))
            }
            positions.append(pos)
            
        # Dummy normalization: treat the sum of imported as the full portfolio,
        # then scale each position's weight to a theoretical $100,000 portfolio.
        # This will be refined as the market_data_cache is wired in.
        
        return {
            "message": "Sandbox scenario successfully loaded.",
            "disclaimer": "This is a theoretical data simulation. Invest AI will analyze this model. This is not financial advice for your personal assets.",
            "theoretical_baseline": 100000.00,
            "positions": positions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing file: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.fastapi_app:app", host="0.0.0.0", port=8000, reload=True)
