import os
import re
import pandas as pd
from sklearn.model_selection import train_test_split

def normalize_description(text):
    """
    Normalize transaction description for consistent feature extraction.
    - Convert to lowercase
    - Normalize unnecessary whitespace
    - Preserves letters, digits, and common separators while keeping keywords.
    """
    if not isinstance(text, str):
        return ""
    
    # Lowercase
    text = text.lower()
    
    # Replace multiple spaces with a single space and strip
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def preprocess_and_split(data_path, test_size=0.2, random_state=42):
    """
    Load, validate, clean, normalize, and split the bank transactions dataset.
    """
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Dataset not found at {data_path}")
        
    df = pd.read_csv(data_path)
    
    # Validate required columns
    required_cols = ["description", "category"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
            
    # Drop rows with missing values in description or category
    df = df.dropna(subset=required_cols)
    
    # Remove duplicate descriptions
    df = df.drop_duplicates(subset=["description"])
    
    # Normalize descriptions
    df["normalized_description"] = df["description"].apply(normalize_description)
    
    # Train-test split (stratified by category)
    train_df, test_df = train_test_split(
        df,
        test_size=test_size,
        stratify=df["category"],
        random_state=random_state
    )
    
    return train_df, test_df

if __name__ == "__main__":
    DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bank_transaction_training_dataset.csv")
    
    try:
        train_df, test_df = preprocess_and_split(DATA_PATH)
        
        total_records = len(train_df) + len(test_df)
        categories = train_df["category"].unique()
        
        print("--- Preprocessing & Split Validation ---")
        print(f"Total records (after deduplication): {total_records}")
        print(f"Training records (80%): {len(train_df)}")
        print(f"Testing records (20%): {len(test_df)}")
        print(f"Number of categories: {len(categories)}")
        
        print("\nClass distribution in Training and Testing sets:")
        train_counts = train_df["category"].value_counts()
        test_counts = test_df["category"].value_counts()
        
        print(f"{'Category':<30} | {'Train Count':<12} | {'Test Count':<10}")
        print("-" * 60)
        for cat in sorted(categories):
            tr_c = train_counts.get(cat, 0)
            te_c = test_counts.get(cat, 0)
            print(f"{cat:<30} | {tr_c:<12} | {te_c:<10}")
            
    except Exception as e:
        print(f"Error during preprocessing validation: {e}")
