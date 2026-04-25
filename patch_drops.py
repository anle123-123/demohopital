import sys
path = "data/SQLQuery1.sql"
try:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
except Exception as e:
    print(f"Error reading file: {e}")
    sys.exit(1)

# Look for the sequence where PHIEUKHAM is dropped before HOSODINHKEM
# We want to swap them or verify the block.

# Note: The spacing in the file might be variable (tabs vs spaces).
# I will instead try to locate the lines individually and re-construct if they are close.

lines = text.splitlines()
idx_phieu = -1
idx_hoso = -1

for i, line in enumerate(lines):
    if "DROP TABLE DBO.PHIEUKHAM" in line:
        idx_phieu = i
    if "DROP TABLE DBO.HOSODINHKEM" in line:
        idx_hoso = i

if idx_phieu != -1 and idx_hoso != -1:
    if idx_phieu < idx_hoso:
        print(f"Found PHIEUKHAM (line {idx_phieu}) dropped BEFORE HOSODINHKEM (line {idx_hoso}). Swapping...")
        # Swap the lines
        lines[idx_phieu], lines[idx_hoso] = lines[idx_hoso], lines[idx_phieu]
        
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("Fixed.")
    else:
        print("Order ok (HOSODINHKEM dropped first).")
else:
    print("Could not find both DROP lines.")
