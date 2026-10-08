import requests, base64
for n, u in (("a", "http://photo-tmdb.com/stalker_portal/misc/logos/320/3867.png?ver=88320"), ("b", "http://photo-tmdb.com/stalker_portal/misc/logos/320/13334.jpg?59189")):
    r = requests.get(u, headers={"User-Agent": "TiviMate/4.7.0"}, timeout=60)
    print(f"::notice::{n} {r.status_code} {r.headers.get('content-type')} {len(r.content)}")
    open(f"probe_{n}.bin", "wb").write(r.content)
