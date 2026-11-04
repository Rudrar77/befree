import os
import joblib
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix
)
from preprocessing import preprocess_and_split

def evaluate_model():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_dir, "data", "bank_transaction_training_dataset.csv")
    model_path = os.path.join(base_dir, "models", "transaction_classifier_v3.joblib")
    reports_dir = os.path.join(base_dir, "reports")
    
    os.makedirs(reports_dir, exist_ok=True)
    
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Main dataset not found at {data_path}.")
        
    # Reconstruct the test split on the fly to avoid depending on disk files
    _, test_df = preprocess_and_split(data_path)
    X_test = test_df["normalized_description"]
    y_test = test_df["category"]
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found at {model_path}. Please run train.py first.")
        
    pipeline = joblib.load(model_path)
    
    # Predict
    y_pred = pipeline.predict(X_test)
    
    # Metrics
    accuracy = accuracy_score(y_test, y_pred)
    macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(y_test, y_pred, average='macro')
    weighted_precision, weighted_recall, weighted_f1, _ = precision_recall_fscore_support(y_test, y_pred, average='weighted')
    
    # Save Report
    report_text = classification_report(y_test, y_pred, digits=4)
    report_save_path = os.path.join(reports_dir, "classification_report_v3.txt")
    with open(report_save_path, "w", encoding="utf-8") as f:
        f.write(report_text)
        
    # Save CM plot
    classes = pipeline.classes_
    cm = confusion_matrix(y_test, y_pred, labels=classes)
    
    plt.figure(figsize=(14, 12))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Purples', xticklabels=classes, yticklabels=classes)
    plt.title('Confusion Matrix V3')
    plt.ylabel('Actual Category')
    plt.xlabel('Predicted Category')
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    plt.tight_layout()
    
    cm_save_path = os.path.join(reports_dir, "confusion_matrix_v3.png")
    plt.savefig(cm_save_path, dpi=300)
    plt.close()
    
    print("--- Model Evaluation Complete ---")
    print(f"Overall Accuracy:  {accuracy:.4f}")
    print(f"Macro F1-score:    {macro_f1:.4f}")
    print(f"Weighted F1-score: {weighted_f1:.4f}")
    print(f"Classification Report saved to: {os.path.relpath(report_save_path, base_dir)}")
    print(f"Confusion Matrix saved to:       {os.path.relpath(cm_save_path, base_dir)}")

if __name__ == "__main__":
    evaluate_model()
