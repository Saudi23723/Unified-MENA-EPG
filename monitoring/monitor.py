#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Real-time monitoring and alerts for IPTV playlist updates.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from epg_lib_retry import get_with_retry, validate_xml_health, safe_parse_xml


class PlaylistMonitor:
    """Monitor IPTV playlist health and updates."""
    
    def __init__(self):
        self.playlist_url = 'https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/ai_sports_dashboard.m3u'
        self.epg_url = 'https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/unified_mena_epg.xml'
        self.status_file = 'monitoring/status.json'
        self.alerts = []
        self.metrics = {
            'last_check': None,
            'playlist_status': 'unknown',
            'epg_status': 'unknown',
            'channels_count': 0,
            'programs_count': 0,
            'uptime': 0,
            'check_interval': 3600  # 1 hour
        }
    
    def check_playlist(self):
        """Check if playlist is accessible and valid."""
        try:
            response = get_with_retry(self.playlist_url, timeout=10)
            content = response.text
            
            # Count channels
            channels = [line for line in content.split('\n') if line.startswith('#EXTINF')]
            self.metrics['channels_count'] = len(channels)
            self.metrics['playlist_status'] = 'online'
            
            print(f"✓ Playlist OK: {len(channels)} channels found")
            return True
            
        except Exception as e:
            self.metrics['playlist_status'] = 'error'
            self.alerts.append(f"Playlist check failed: {str(e)}")
            print(f"✗ Playlist error: {str(e)}")
            return False
    
    def check_epg(self):
        """Check if EPG is accessible and valid."""
        try:
            response = get_with_retry(self.epg_url, timeout=15)
            content = response.content
            
            # Parse XML
            root = safe_parse_xml(content, 'EPG')
            
            # Validate health
            if validate_xml_health(root, min_channels=1, min_programs=10):
                channels = root.findall('channel')
                programs = root.findall('programme')
                
                self.metrics['epg_status'] = 'online'
                self.metrics['programs_count'] = len(programs)
                
                print(f"✓ EPG OK: {len(channels)} channels, {len(programs)} programs")
                return True
            else:
                self.metrics['epg_status'] = 'warning'
                self.alerts.append('EPG health check failed')
                return False
                
        except Exception as e:
            self.metrics['epg_status'] = 'error'
            self.alerts.append(f"EPG check failed: {str(e)}")
            print(f"✗ EPG error: {str(e)}")
            return False
    
    def check_m3u_streams(self):
        """Verify that stream URLs are accessible."""
        try:
            response = get_with_retry(self.playlist_url, timeout=10)
            content = response.text
            
            stream_urls = []
            for line in content.split('\n'):
                if line.startswith('http'):
                    stream_urls.append(line.strip())
            
            failed = 0
            for url in stream_urls[:3]:  # Check first 3 streams
                try:
                    resp = requests.head(url, timeout=5, allow_redirects=True)
                    if resp.status_code < 400:
                        print(f"✓ Stream OK: {url[:60]}...")
                    else:
                        failed += 1
                        print(f"⚠ Stream warning: {url[:60]}... (HTTP {resp.status_code})")
                except:
                    failed += 1
                    print(f"✗ Stream error: {url[:60]}...")
            
            return failed == 0
            
        except Exception as e:
            print(f"✗ Stream check error: {str(e)}")
            return False
    
    def generate_report(self):
        """Generate monitoring report."""
        self.metrics['last_check'] = datetime.utcnow().isoformat()
        
        report = {
            'timestamp': self.metrics['last_check'],
            'status': 'healthy' if self.metrics['playlist_status'] == 'online' and self.metrics['epg_status'] == 'online' else 'warning',
            'metrics': self.metrics,
            'alerts': self.alerts
        }
        
        return report
    
    def save_status(self):
        """Save monitoring status to file."""
        report = self.generate_report()
        
        os.makedirs(os.path.dirname(self.status_file), exist_ok=True)
        with open(self.status_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📊 Status saved to {self.status_file}")
    
    def run_full_check(self):
        """Run complete health check."""
        print("\n" + "="*60)
        print(f"📊 IPTV Playlist Health Check - {datetime.utcnow().isoformat()}")
        print("="*60 + "\n")
        
        self.check_playlist()
        self.check_epg()
        self.check_m3u_streams()
        
        self.save_status()
        
        report = self.generate_report()
        print(f"\n📈 Status: {report['status'].upper()}")
        
        if self.alerts:
            print(f"\n⚠️  Alerts ({len(self.alerts)}):")
            for alert in self.alerts:
                print(f"  - {alert}")
        
        return report


if __name__ == '__main__':
    monitor = PlaylistMonitor()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'daemon':
        # Run as daemon
        print("Starting monitoring daemon...")
        while True:
            try:
                monitor.run_full_check()
                time.sleep(monitor.metrics['check_interval'])
            except KeyboardInterrupt:
                print("\nMonitoring stopped.")
                break
    else:
        # Single run
        monitor.run_full_check()
