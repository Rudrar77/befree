import os
import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from preprocessing import preprocess_and_split

def train_model():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_dir, "data", "bank_transaction_training_dataset.csv")
    model_dir = os.path.join(base_dir, "models")
    model_path = os.path.join(model_dir, "transaction_classifier_v3.joblib")
    
    os.makedirs(model_dir, exist_ok=True)
    
    # Load and split (stratified 80/20 split)
    train_df, test_df = preprocess_and_split(data_path)
    
    X_train = train_df["normalized_description"]
    y_train = train_df["category"]
    
    # Pipeline with optimized V3 hyperparameters
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1, 1), sublinear_tf=True, min_df=1)),
        ('clf', LogisticRegression(C=5, max_iter=1000, random_state=42))
    ])
    
    # Train
    pipeline.fit(X_train, y_train)
    
    # Save
    joblib.dump(pipeline, model_path)
    
    tfidf_step = pipeline.named_steps['tfidf']
    num_features = len(tfidf_step.get_feature_names_out())
    
    print("--- Model Training Complete ---")
    print(f"Training records: {len(X_train)}")
    print(f"Testing records:  {len(test_df)}")
    print(f"TF-IDF feature count: {num_features}")
    print(f"Model path: {os.path.relpath(model_path, base_dir)}")

if __name__ == "__main__":
    train_model()
