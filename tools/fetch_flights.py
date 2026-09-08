#!/usr/bin/env python3
"""Keyless live ADS-B refresh for channel 6.

Accumulates every tracked flight seen since UTC midnight so the channel shows
the full day so far, not only aircraft airborne at this instant. Flights that
were airborne earlier and are no longer in the feed are kept and marked LANDED.
The list resets automatically at UTC midnight.
"""
import argparse,datetime,json,os,urllib.request

AIRLINES={"ETD":"EY","UAE":"EK","RJA":"RJ","FDB":"FZ","THY":"TK"}
FEED="https://data-cloud.flightradar24.com/zones/fcgi/feed.js?bounds=90,-90,-180,180"
def clean(v): return str(v or "").strip().upper()
def now_utc(): return datetime.datetime.now(datetime.timezone.utc)
def minute_now():
 n=now_utc(); return n.hour*60+n.minute
def get_live():
 q=urllib.request.Request(FEED,headers={"User-Agent":"Mozilla/5.0 (compatible; Unified-MENA-EPG/1.0)","Accept":"application/json"})
 with urllib.request.urlopen(q,timeout=60) as r: data=json.load(r)
 out=[]
 for v in data.values():
  if not isinstance(v,list) or len(v)<19: continue
  call,icao=clean(v[16]),clean(v[18])
  match=next((x for x in AIRLINES if icao==x or call.startswith(x)),None)
  if not match: continue
  origin,dest=clean(v[11]),clean(v[12])
  if not origin or not dest: continue
  out.append({"code":AIRLINES[match],"callsign":call or match,"o":origin,"d":dest,"ac":clean(v[8]) or clean(v[9]) or "\u2014","lat":v[1],"lon":v[2],"alt":v[4]})
 return out
def choose(flights,live,used):
 choices=[(i,f) for i,f in enumerate(flights) if i not in used and f.get("code")==live["code"] and clean(f.get("o"))==live["o"] and clean(f.get("d"))==live["d"]]
 now=minute_now()
 return min(choices,key=lambda x:abs(((x[1].get("dep") or now)%1440)-now))[0] if choices else None
def main():
 p=argparse.ArgumentParser();p.add_argument("--out",required=True);a=p.parse_args()
 try:
  with open(a.out) as h: cache=json.load(h)
 except Exception: cache={"flights":[]}
 today=now_utc().strftime("%Y-%m-%d")
 flights=cache.get("flights") or []
 errors=[]
 if cache.get("date") and cache.get("date")!=today:
  # new UTC day: start the day's accumulation from scratch
  flights=[]
 try: live=get_live()
 except Exception as e: live=[];errors.append(f"live feed unavailable: {e}")
 used=set();matched=0;now=minute_now()
 for item in live:
  i=choose(flights,item,used)
  if i is not None:
   used.add(i);flights[i].update({"api_status":"ACTIVE","lat":item["lat"],"lon":item["lon"],"alt":item["alt"],"ac":item["ac"],"callsign":item["callsign"],"last_seen":now});matched+=1
  else:
   flights.append({"code":item["code"],"num":item["callsign"],"o":item["o"],"d":item["d"],"dep":max(0,now-60),"arr":now+120,"ac":item["ac"],"api_status":"ACTIVE","delay":0,"lat":item["lat"],"lon":item["lon"],"alt":item["alt"],"callsign":item["callsign"],"first_seen":now,"last_seen":now})
 # anything seen earlier today but no longer airborne -> keep it, mark landed
 if live:
  for i,f in enumerate(flights):
   if i in used: continue
   if f.get("api_status")=="ACTIVE" or f.get("last_seen") is not None:
    f["api_status"]="LANDED";f["lat"]=None;f["lon"]=None;f["alt"]=None
 unique={}
 for f in flights: unique[(f.get("code"),f.get("num"),f.get("o"),f.get("d"))]=f
 flights=sorted(unique.values(),key=lambda f:(f.get("dep",9999),f.get("num","")))
 codes=("EY","EK","RJ","FZ","TK")
 counts={c:sum(x["code"]==c for x in live) for c in codes}
 day_counts={c:sum(x.get("code")==c for x in flights) for c in codes}
 payload={"generated_utc":now_utc().isoformat(timespec="seconds"),"date":today,"source":"keyless live ADS-B feed (accumulated since UTC midnight)","live_counts":counts,"day_counts":day_counts,"live_total":len(live),"matched_schedule_rows":matched,"errors":errors,"flights":flights}
 os.makedirs(os.path.dirname(a.out) or ".",exist_ok=True)
 with open(a.out,"w") as h: json.dump(payload,h,indent=1)
 print(f"live={len(live)} matched={matched} day_total={len(flights)} live_counts={counts} day_counts={day_counts}")
if __name__=="__main__": main()
