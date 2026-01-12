import re
import time

def extract_project_detail_id(url):
    match = re.search(r'project_detail_id=([a-zA-Z0-9]+)', url)
    return match.group(1) if match else None

def format_project_url(campaign_id, project_detail_id, base_url):
    return f"{base_url}/homeCampaigns/?campaign_id={campaign_id}&project_detail_id={project_detail_id}"

def clean_text(text):
    return text.strip() if text else ""
