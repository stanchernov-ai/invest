import yfinance as yf
import json
import os

def scrub():
    print("Scrubbing SPY...")
    spy = yf.download("SPY", period="5y")
    print("Scrubbing QQQ...")
    qqq = yf.download("QQQ", period="5y")
    
    data = {}
    for date, row in spy.iterrows():
        d_str = date.strftime("%Y%m%d")
        data[d_str] = {"spy": round(float(row["Close"].iloc[0]), 2)}
        
    for date, row in qqq.iterrows():
        d_str = date.strftime("%Y%m%d")
        if d_str in data:
            data[d_str]["qqq"] = round(float(row["Close"].iloc[0]), 2)
            
    out_path = os.path.join(os.path.dirname(__file__), "..", "src", "data", "static_benchmarks.json")
    with open(out_path, "w") as f:
        json.dump(data, f)
    print(f"Saved to {out_path}")

if __name__ == "__main__":
    scrub()