
import requests

def test_api():
    try:
        # Assuming the backend is running on localhost:8000
        # and we need an auth token. 
        # But wait, looking at the logs, it seems the user is running the app.
        response = requests.get("http://localhost:8000/products/")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("Success! Product list loaded.")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    test_api()
