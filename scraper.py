import requests
from bs4 import BeautifulSoup
import json
import os

def grab_epg():
    url = "https://www.aljazeera.net/schedule"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        print("جاري سحب البيانات...")
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        
        soup = BeautifulSoup(r.text, 'html.parser')
        script = soup.find('script', id='__NEXT_DATA__')
        
        if not script:
            print("خطأ: لم يتم العثور على البيانات في الصفحة.")
            return

        data = json.loads(script.string)
        programs = data.get('props', {}).get('pageProps', {}).get('schedule', [])
        
        if not programs:
            print("تنبيه: لا توجد برامج مجدولة حالياً.")
            return

        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n'
        xml += '  <channel id="Aljazeera.Arabic">\n    <display-name>Al Jazeera Arabic</display-name>\n  </channel>\n'
        
        for p in programs:
            title = p.get('title', 'Unknown')
            start = p.get('startDate', '').replace('-', '').replace(':', '').replace('T', '').split('.')[0]
            xml += f'  <programme start="{start} +0300" channel="Aljazeera.Arabic">\n'
            xml += f'    <title lang="ar">{title}</title>\n'
            xml += '  </programme>\n'
            
        xml += '</tv>'
        
        # حفظ الملف في المجلد الحالي
        filename = "aljazeera_epg.xml"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(xml)
        
        if os.path.exists(filename):
            print(f"تم إنشاء الملف بنجاح: {os.path.abspath(filename)}")
        else:
            print("خطأ: فشل حفظ الملف.")
            
    except Exception as e:
        print(f"حدث خطأ غير متوقع: {e}")

if __name__ == "__main__":
    grab_epg()
