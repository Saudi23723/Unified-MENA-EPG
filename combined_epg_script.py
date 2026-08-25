import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import time
import xml.dom.minidom

# --- إعدادات عامة ---
OUTPUT_FILE = "combined_epg_final.xml"
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def format_unix_time(unix_ts_ms, is_ms=True):
    """تحويل الطابع الزمني إلى تنسيق XMLTV"""
    ts = unix_ts_ms / 1000.0 if is_ms else unix_ts_ms
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime('%Y%m%d%H%M%S +0000')

def fetch_shahid(root):
    print("📡 جاري جلب بيانات Shahid...")
    channel_ids = "387238,387251,387296,387290,387293,49923122575716,387294,387937,400919,946945,946940,946938,995495,999927,49923088749329,49923068171559,49923697545394,946946,49923697648201,49923697657389,946942,49923691806580,49923697659290,49923120452582,49923088717401,49923088781412,49923697650617,49923697642137,49923088814140,49923697342447,49923712885383,969745,977946,975435,963543,1005232,49923086870104,988045,992538,983124,976272,409385,409390,387286,387288,946948,862837,49923569816895,1003218,49923693965985,49923446898171,49923639151416,997605,1001845,49923434082342,409387,418308,400917,400921,400924,989622,986064,986069,951783,49922904934759,986346,986014,986024,49923172117967,49922763891977,49923172215352,49922763510387,49923518527492,414449,1029746,388567,388566,49923697660442"
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z")
    to_date = (now + timedelta(days=2)).strftime("%Y-%m-%dT23:59:59.000Z")
    url = f"https://api3.shahid.net/proxy/v2.1/shahid-epg-api/?csvChannelIds={channel_ids}&language=ar&from={from_date}&to={to_date}&country=SA"
    
    try:
        data = requests.get(url, headers=HEADERS).json().get('items', [])
        for channel in data:
            ch_id = f"Shahid_{channel.get('channelId')}"
            if root.find(f"channel[@id='{ch_id}']") is None:
                chan_el = ET.SubElement(root, "channel", id=ch_id)
                ET.SubElement(chan_el, "display-name").text = f"Shahid {channel.get('channelId')}"
            
            for p in channel.get('items', []):
                start = p['from'].split('.')[0].replace('-', '').replace(':', '').replace('T', '') + " +0000"
                stop = p['to'].split('.')[0].replace('-', '').replace(':', '').replace('T', '') + " +0000"
                prog = ET.SubElement(root, "programme", start=start, stop=stop, channel=ch_id)
                ET.SubElement(prog, "title", lang="ar").text = p.get('title', 'N/A')
                ET.SubElement(prog, "desc", lang="ar").text = p.get('description', '')
                if p.get('productPoster'):
                    img = p['productPoster'].replace('{height}', '400').replace('{width}', '600').replace('{croppingPoint}', 'original')
                    ET.SubElement(prog, "icon", src=img)
    except Exception as e: print(f"⚠️ خطأ في Shahid: {e}")

def fetch_starzplay(root):
    print("📡 جاري جلب بيانات Starzplay...")
    base_url = 'https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp'
    now_ts = int(time.time())
    # تم ضبط المدى الزمني هنا ليشمل 3 أيام تلقائياً
    params = {'ts_start': now_ts - 86400, 'ts_end': now_ts + (86400 * 3), 'lang': 'ar', 'pg': 18, 'category': 'all', 'page': 1, 'limit': 40, 'x-geo-country': 'SA'}
    
    try:
        data = requests.get(base_url, params=params, headers=HEADERS).json()
        for channel in data.get('data', []):
            slug = f"Starz_{channel.get('slug')}"
            if root.find(f"channel[@id='{slug}']") is None:
                chan_el = ET.SubElement(root, "channel", id=slug)
                ET.SubElement(chan_el, "display-name").text = channel.get('title', slug)
                images = channel.get('images', [])
                if images:
                    logo = next((img for img in images if img.get('type') == 'logo-png'), images[0])
                    ET.SubElement(chan_el, "icon", src=logo.get('url', ''))

            for event in channel.get('events', []):
                prog = ET.SubElement(root, "programme", start=format_unix_time(event.get('tsStart'), False), 
                                    stop=format_unix_time(event.get('tsEnd'), False), channel=slug)
                ET.SubElement(prog, "title", lang="ar").text = event.get('title', 'Unknown')
                ET.SubElement(prog, "desc", lang="ar").text = event.get('description', '')
                if event.get('images'): ET.SubElement(prog, "icon", src=event['images'][0].get('url', ''))
    except Exception as e: print(f"⚠️ خطأ في Starzplay: {e}")

def fetch_stc_tv_3_days(root):
    """جلب بيانات STC TV لـ 3 أيام متتالية"""
    for i in range(3):
        date_str = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
        print(f"📡 [STC TV] جاري جلب بيانات يوم: {date_str}...")
        url = f"https://prod-cdn-content-api.intigral-ott.net/content-api-3.0.1/channels/schedules/{date_str}/3?apikey=GDMPrdExy0sVDlZMzNDdUyZ&country=SA"
        
        try:
            data = requests.get(url, headers=HEADERS).json()
            for ch_data in data:
                raw_id = ch_data.get('channelId', '').split('/')[-1]
                ch_id = f"STC_{raw_id}"
                
                # إضافة القناة فقط إذا لم تكن موجودة مسبقاً (لتجنب التكرار في الأيام اللاحقة)
                # The schedule endpoint returns only channelId and listings -
                # no name and no logo - so the numeric id is genuinely all
                # there is to show here. Naming these properly needs
                # intigral's separate channel-metadata endpoint.
                if root.find(f"channel[@id='{ch_id}']") is None:
                    chan_el = ET.SubElement(root, "channel", id=ch_id)
                    ET.SubElement(chan_el, "display-name").text = f"STC Channel {raw_id}"
                
                for list_item in ch_data.get('listings', []):
                    start_t = list_item.get('startTime')
                    end_t = list_item.get('endTime')
                    if start_t and end_t:
                        prog = ET.SubElement(root, "programme", start=format_unix_time(start_t), stop=format_unix_time(end_t), channel=ch_id)
                        title = list_item.get('localizedTitle', {}).get('ar') or list_item.get('title', '')
                        ET.SubElement(prog, "title", lang="ar").text = title
                        desc = list_item.get('localizedDescription', {}).get('ar') or list_item.get('description', '')
                        if desc: ET.SubElement(prog, "desc", lang="ar").text = desc
                        imgs = list_item.get('images', [])
                        if imgs: ET.SubElement(prog, "icon", src=imgs[0].get('imageUrl', ''))
        except Exception as e: print(f"⚠️ خطأ في STC TV ليوم {date_str}: {e}")

def main():
    print("🚀 بدء عملية الدمج لـ 3 أيام...")
    root = ET.Element("tv", {"generator-info-name": "Multi-Source EPG Generator"})

    fetch_shahid(root)
    fetch_starzplay(root)
    fetch_stc_tv_3_days(root) # استدعاء الدالة الجديدة لـ 3 أيام

    print("💾 جاري حفظ الملف النهائي...")
    xml_str = ET.tostring(root, encoding="utf-8")
    reparsed = xml.dom.minidom.parseString(xml_str)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
        
    print(f"✅ تم بنجاح! الملف يحتوي الآن على برامج لـ 3 أيام: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
