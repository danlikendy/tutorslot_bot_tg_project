from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN = Path("app/integrations/token.json")

creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)

service = build("calendar", "v3", credentials=creds)

calendar = service.calendarList().get(calendarId="primary").execute()
print("Календарь успешно доступен:", calendar["summary"])