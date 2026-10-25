import os
import glob
import pandas as pd

def main():
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_dir = os.path.join(repo_dir, "dataset")
    csv_files = sorted(glob.glob(os.path.join(dataset_dir, "*.csv")))
    
    print(f"Found {len(csv_files)} CSV files in {dataset_dir}:\n")
    for csv_file in csv_files:
        rel_name = os.path.basename(csv_file)
        print("=" * 80)
        print(f"FILE: {rel_name}")
        df = pd.read_csv(csv_file)
        print(f"SHAPE: {df.shape}")
        print(f"COLUMNS: {list(df.columns)}")
        print("\nFIRST 3 ROWS:")
        print(df.head(3))
        print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
