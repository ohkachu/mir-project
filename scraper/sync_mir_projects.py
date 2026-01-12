import sys
import argparse
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from supabase import create_client
from loguru import logger
from config import SUPABASE_URL, SUPABASE_KEY, MAKE_IT_REAL_BASE_URL, SYNC_DELAY, LOG_FILE, LOG_LEVEL
from utils import extract_project_detail_id, format_project_url

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)
logger.add(LOG_FILE, rotation="10 MB", level=LOG_LEVEL)

MIR_HEADERS = {
    'gtoken': '6c43512e7ec53ebd55098e45c539d146',
    'x-auth-token': '48d1faf76e34be3603234fe260770338e7ad8545398ed973'
}

class MIRProjectScraper:
    def __init__(self, campaign_tag):
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.driver = None
        self.campaign_tag = campaign_tag

    def init_driver(self):
        logger.info("正在初始化浏览器...")
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("✓ 浏览器初始化成功")

    def close_driver(self):
        if self.driver:
            self.driver.quit()

    def fetch_campaign_projects(self, campaign_id):
        url = f"{MAKE_IT_REAL_BASE_URL}/homeCampaigns/?campaign_id={campaign_id}"
        logger.info(f"访问: {url}")
        self.driver.get(url)
        time.sleep(5)

        # 滚动加载
        for i in range(10):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        project_ids = self.driver.execute_script("""
            const links = Array.from(document.querySelectorAll('a[href*="project_detail_id"]'));
            return [...new Set(links.map(l => {
                const m = l.href.match(/project_detail_id=([a-zA-Z0-9]+)/);
                return m ? m[1] : null;
            }).filter(id => id))];
        """)
        logger.info(f"✓ 找到 {len(project_ids)} 个作品")
        return project_ids

    def fetch_project_detail(self, campaign_id, project_detail_id):
        url = format_project_url(campaign_id, project_detail_id, MAKE_IT_REAL_BASE_URL)
        self.driver.get(url)
        time.sleep(4)
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        data = self.driver.execute_script("""
            const getText = sel => document.querySelector(sel)?.textContent.trim() || null;
            const getAll = sel => Array.from(document.querySelectorAll(sel)).map(e => e.textContent.trim());
            const getImages = () => Array.from(document.querySelectorAll('img'))
                .map(img => img.src).filter(src => src && src.startsWith('http') && !src.includes('logo'));

            return {
                title: getText('h1'),
                description: getText('[class*="description"]'),
                instructions: getText('[class*="instruction"]'),
                author_name: getText('[class*="author"]'),
                tags: getAll('.tag, [class*="tag"]'),
                images: getImages(),
                cover_image: getImages()[0] || null,
                view_count: 0,
                like_count: 0,
                print_count: 0
            };
        """)

        if not data or self.campaign_tag not in data.get('tags', []):
            logger.info(f"✗ 作品 {project_detail_id} 不包含 tag '{self.campaign_tag}'")
            return None

        logger.info(f"✓ 匹配: {data.get('title', '无标题')}")
        data.update({
            'project_detail_id': project_detail_id,
            'project_url': url,
            'crafts': [],
            'materials': [],
            'is_featured': False
        })
        return data

    def save_project(self, campaign_uuid, project_data):
        project_data['campaign_id'] = campaign_uuid
        result = self.supabase.table('projects').select('id').eq(
            'project_detail_id', project_data['project_detail_id']
        ).execute()

        if result.data:
            self.supabase.table('projects').update(project_data).eq('id', result.data[0]['id']).execute()
            return True, False
        else:
            self.supabase.table('projects').insert(project_data).execute()
            return True, True

    def sync_campaign(self, campaign_id):
        logger.info(f"开始同步活动 {campaign_id}, tag: {self.campaign_tag}")
        self.init_driver()
        
        # 确保活动存在
        result = self.supabase.table('campaigns').select('id').eq('campaign_id', campaign_id).execute()
        if result.data:
            campaign_uuid = result.data[0]['id']
        else:
            logger.error("活动不存在")
            return

        project_ids = self.fetch_campaign_projects(campaign_id)
        stats = {'total': len(project_ids), 'matched': 0, 'new': 0, 'updated': 0}

        for i, pid in enumerate(project_ids, 1):
            logger.info(f"进度: {i}/{len(project_ids)}")
            data = self.fetch_project_detail(campaign_id, pid)
            if data:
                stats['matched'] += 1
                success, is_new = self.save_project(campaign_uuid, data)
                if success:
                    stats['new' if is_new else 'updated'] += 1
            time.sleep(SYNC_DELAY)

        self.close_driver()
        logger.info(f"完成! 匹配: {stats['matched']}, 新增: {stats['new']}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign-id', required=True)
    parser.add_argument('--campaign-tag', required=True)
    args = parser.parse_args()
    
    scraper = MIRProjectScraper(args.campaign_tag)
    scraper.sync_campaign(args.campaign_id)

if __name__ == '__main__':
    main()
