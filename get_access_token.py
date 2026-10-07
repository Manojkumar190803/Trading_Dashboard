from fyers_apiv3 import fyersModel

APP_ID = "TEFURYVFBX-100"
SECRET_ID = "PDIWQ2VJW8"
REDIRECT_URL = "http://localhost:8080"

# Step 1: Initialize client
client = fyersModel.Client(
    client_id=APP_ID,
    secret_key=SECRET_ID,
    redirect_url=REDIRECT_URL,
    grant_type="authorization_code"
)

# Step 2: Generate auth URL
print("=" * 80)
print("STEP 1: Open this URL in your browser and authenticate")
print("=" * 80)
auth_url = client.generate_authcode()
print(f"\n{auth_url}\n")

print("=" * 80)
print("STEP 2: After login, you'll be redirected to:")
print("http://localhost:8080?auth_code=XXXXXXXXXXXXXX")
print("Copy the auth_code from the URL (the long string after auth_code=)")
print("=" * 80)

# Step 3: Set the auth code (replace with actual code from step 2)
AUTH_CODE = input("\nPaste the auth_code here: ").strip()

if AUTH_CODE:
    client.set_auth_code(AUTH_CODE)
    response = client.generate_token()
    
    if "access_token" in response:
        access_token = response['access_token']
        print("\n" + "=" * 80)
        print("SUCCESS! Here's your Access Token:")
        print("=" * 80)
        print(f"\n{access_token}\n")
        print("=" * 80)
        print("Use this token for OpenAlgo WebSocket authentication")
        print("=" * 80)
    else:
        print(f"Error: {response}")
else:
    print("No auth code provided")
