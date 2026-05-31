import os
import glob
import re

replacements = [
    ("STRONG BUY", "HIGH CONVICTION (OVERWEIGHT)"),
    ("Strong Buy", "High Conviction (Overweight)"),
    ("STRONG SELL", "STRONG BEARISH (LIQUIDATE)"),
    ("Strong Sell", "Strong Bearish (Liquidate)"),
    ("BUY", "ACCUMULATE CANDIDATE"),
    ("Buy", "Accumulate Candidate"),
    ("TRIM", "REDUCE EXPOSURE"),
    ("Trim", "Reduce Exposure"),
    ("SELL", "BEARISH (LIQUIDATE)"),
    ("Sell", "Bearish (Liquidate)"),
    ("Today's Actions", "Theoretical Scenario Adjustments"),
    ("Today\\'s Actions", "Theoretical Scenario Adjustments"),
]

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    # Order matters! STRONG BUY before BUY, STRONG SELL before SELL
    for old, new in replacements:
        # We want to replace whole words or exact strings where it makes sense, but the simplest is direct replace since these are specific terms.
        # However, "Buy" can be a substring in "Buy/Strong Buy". We already do "Strong Buy" first.
        # Let's use regex with word boundaries to avoid replacing parts of other words (like "Selling" -> "Bearish (Liquidate)ing").
        # Wait, "Buy" is inside "MAX 3 BUYS" or "buy_side=4/5". 
        # So a pure text replace might be risky for "Buy" and "Sell". 
        
        # Let's do exact match replace for the specific Python sets and JSON fields.
        content = re.sub(rf'\b{re.escape(old)}\b', new, content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

# Target directories
target_dirs = ['src/**/*.py', 'tests/**/*.py']
for target_dir in target_dirs:
    for filepath in glob.glob(target_dir, recursive=True):
        process_file(filepath)

print("Lexical lobotomy complete.")
