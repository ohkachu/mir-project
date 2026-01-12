import sys
import argparse
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from supabase import create_client
from loguru import logger

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
MAKE_IT_REAL_BASE_URL = "https://makeitreal-beta.eufymake.com"

logger.remove()
logger.add(sys.stderr, level="INFO")

class MIRProjectScraper:
    def __init__(self, campaign_tag):
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.driver = None
        self.campaign_tag = campaign_tag

    def init_driver(self):
        logger.info("初始化浏览器...")
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        service = Service('/usr/local/bin/chromedriver')
        self.driver = webdriver.Chrome(service=service, options=options)
        logger.info("✓ 浏览器就绪")

    def close_driver(self):
        if self.driver:
            self.driver.quit()

    def fetch_projects(self, campaign_id):
        url = f"{MAKE_IT_REAL_BASE_URL}/homeCampaigns/?campaign_id={campaign_id}"
        logger.info(f"访问: {url}")
        self.driver.get(url)
        time.sleep(5)
        
        for i in range(10):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        
        ids = self.driver.execute_script("""
            const links = Array.from(document.querySelectorAll('a[href*="project_detail_id"]'));
            return [...new Set(links.map(l => {
                const m = l.href.match(/project_detail_id=([a-zA-Z0-9]+)/);
                return m ? m[1] : null;
            }).filter(id => id))];
        """)
        logger.info(f"✓ 找到 {len(ids)} 个作品")
        return ids

    def fetch_detail(self, campaign_id, pid):
        url = f"{MAKE_IT_REAL_BASE_URL}/homeCampaigns/?campaign_id={campaign_id}&project_detail_id={pid}"
        self.driver.get(url)
        time.sleep(4)
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        data = self.driver.execute_script("""
            const get = s => document.querySelector(s)?.textContent.trim() || null;
            const getAll = s => Array.from(document.querySelectorAll(s)).map(e => e.textContent.trim());
            const imgs = Array.from(document.querySelectorAll('img')).map(i => i.src).filter(s => s.startsWith('http') && !s.includes('logo'));
            
            return {
                title: get('h1'),
                description: get('[class*="description"]'),
                instructions: get('[class*="instruction"]'),
                author_name: get('[class*="author"]'),
                tags: getAll('.tag, [class*="tag"]'),
                images: imgs,
                cover_image: imgs[0] || null,
                view_count: 0,
                like_count: 0,
                print_count: 0
            };
        """)
        
        if not data or self.campaign_tag not in data.get('tags', []):
            return None
        
        data.update({
            'project_detail_id': pid,
            'project_url': url,
            'crafts': [],
            'materials': [],
            'is_featured': False
        })
        return data

    def save(self, campaign_uuid, data):
        data['campaign_id'] = campaign_uuid
        result = self.supabase.table('projects').select('id').eq('project_detail_id', data['project_detail_id']).execute()
        
        if result.data:
            self.supabase.table('projects').update(data).eq('id', result.data[0]['id']).execute()
            return True, False
        else:
            self.supabase.table('projects').insert(data).execute()
            return True, True

    def sync(self, campaign_id):
        logger.info(f"开始同步活动 {campaign_id}, tag: {self.campaign_tag}")
        
        try:
            self.init_driver()
            result = self.supabase.table('campaigns').select('id').eq('campaign_id', campaign_id).execute()
            if not result.data:
                logger.error("活动不存在")
                return
            
            campaign_uuid = result.data[0]['id']
            project_ids = self.fetch_projects(campaign_id)
            
            stats = {'total': len(project_ids), 'matched': 0, 'new': 0}
            
            for i, pid in enumerate(project_ids, 1):
                logger.info(f"进度: {i}/{len(project_ids)}")
                data = self.fetch_detail(campaign_id, pid)
                if data:
                    stats['matched'] += 1
                    success, is_new = self.save(campaign_uuid, data)
                    if success and is_new:
                        stats['new'] += 1
                time.sleep(1)
            
            logger.info(f"完成! 匹配: {stats['matched']}, 新增: {stats['new']}")
        finally:
            self.close_driver()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign-id', required=True)
    parser.add_argument('--campaign-tag', required=True)
    args = parser.parse_args()
    scraper = MIRProjectScraper(args.campaign_tag)
    scraper.sync(args.campaign_id)

if __name__ == '__main__':
    main()
