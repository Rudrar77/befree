import os
import joblib
from preprocessing import normalize_description

class TransactionClassifier:
    def __init__(self, model_path=None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if model_path is None:
            model_path = os.path.join(base_dir, "models", "transaction_classifier_v3.joblib")
            
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found at {model_path}. Please complete model tuning first.")
            
        # Load the saved pipeline containing TF-IDF vectorizer and Logistic Regression model
        self.pipeline = joblib.load(model_path)
        self.classes_ = self.pipeline.named_steps['clf'].classes_
        
    def predict(self, descriptions):
        """
        Predict categories and confidence scores for a list of transaction descriptions.
        """
        if isinstance(descriptions, str):
            descriptions = [descriptions]
            
        # 1. Apply the exact same preprocessing normalization used during training
        normalized_descs = [normalize_description(desc) for desc in descriptions]
        
        # 2. Use the pipeline to predict
        predictions = self.pipeline.predict(normalized_descs)
        probabilities = self.pipeline.predict_proba(normalized_descs)
        
        results = []
        for pred, proba in zip(predictions, probabilities):
            # Get probability score of the predicted class
            class_idx = list(self.classes_).index(pred)
            confidence = proba[class_idx]
            results.append({
                'category': pred,
                'confidence': confidence
            })
            
        return results

if __name__ == "__main__":
    # Demo running realistic transaction descriptions
    try:
        classifier = TransactionClassifier()
        
        test_examples = [
            "UPI/Swiggy Order",
            "POS Card Purchase at H&M",
            "Netflix Monthly Subscription",
            "Apollo Pharmacy",
            "ATM Cash Withdrawal",
            "Monthly Salary Credit",
            "Electricity Bill Payment",
            "Myntra Online Purchase"
        ]
        
        predictions = classifier.predict(test_examples)
        
        print("--- Classification Prediction Demo ---")
        for tx, pred in zip(test_examples, predictions):
            print(f"Transaction:        {tx}")
            print(f"Predicted Category: {pred['category']}")
            print(f"Confidence:         {pred['confidence']:.4f}")
            print("-" * 40)
            
    except Exception as e:
        print(f"Error initializing or running classifier demo: {e}")
