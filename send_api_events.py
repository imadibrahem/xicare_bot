import asyncio
import pandas as pd
import json
from datetime import datetime, timedelta
import time
from dotenv import dotenv_values

from get_api_events import get_api_events
from analyze_api_events import analyze_api_events
from smtp2go_send_email import smtp2go_send_email, smtp2go_activity_by_email_id

def send_api_events(scope):
    print("Start send_api_events()")
    # 1. get_api_events()
    out_path = asyncio.run(get_api_events())
    
    # 2. analyze_api_events()
    start = (datetime.now() - timedelta(weeks=1)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    start =pd.Timestamp(start)
    end = pd.Timestamp(end)
    outdir = analyze_api_events(path_api=out_path, start=start, end=end, bucket="1d")
    
    # 3.1 smtp2go_send_email() regular users
    config = dotenv_values()
    send_resp = smtp2go_send_email(
        api_key=config["smtp2go_api_key"],
        sender=config["mail_sender"],
        to=json.loads(config["mail_to_statistics"]),
        cc=json.loads(config["mail_cc_statistics"]) if config.get("mail_cc_statistics") else None,
        subject=f"DIWI Statistik Update {start.strftime("%d-%m-%Y")} bis {end.strftime("%d-%m-%Y")}",
        text_body=f"Im Anhang die Statistiken von DIWI für den Zeitraum {start.strftime("%d-%m-%Y")} bis {end.strftime("%d-%m-%Y")}",
        attachments=[
                {
                    "filename": f"{outdir}/kpis_api_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png",
                    "mimetype": "image/png"
                }
            ]
        )
    
    # 3.2 smtp2go_activity_by_email_id() regular users
    email_id = send_resp["data"]["email_id"]
    time.sleep(20)
    print(email_id)
    

    activity = smtp2go_activity_by_email_id(
        api_key=config["smtp2go_api_key"],
        email_id=email_id,
    )
    print(activity)
    
    # 4.1 smtp2go_send_email() admins
    send_resp = smtp2go_send_email(
        api_key=config["smtp2go_api_key"],
        sender=config["mail_sender"],
        to=json.loads(config["mail_to_data"]),
        cc=json.loads(config["mail_cc_data"]) if config.get("mail_cc_data") else None,
        subject=f"DIWI Daten Update bis {end.strftime("%d-%m-%Y")}",
        text_body=f"Im Anhang die Datem von DIWI von Anfang bis {end.strftime("%d-%m-%Y")}",
        attachments=[
                {
                    "filename": f"{out_path}",
                    "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                }
            ]
        )
    
    # 4.2 smtp2go_activity_by_email_id() admins
    email_id = send_resp["data"]["email_id"]
    time.sleep(20)
    print(email_id)    

    activity = smtp2go_activity_by_email_id(
        api_key=config["smtp2go_api_key"],
        email_id=email_id,
    )
    print(activity)
    
    print("End send_api_events()")
    
    
if __name__ == "__main__":
    send_api_events()
    
    