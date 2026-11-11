# SAUDI.TV for Samsung TVs (Tizen)

A Samsung TV does not run Android apps, so this is a separate app: a Tizen web app (HTML + JavaScript, Samsung's
AVPlay player). First version, **not yet tried on a real Samsung TV**:

- activation by device code on the same admin site, the device's playlists
- Live TV: groups, channels, full screen, CH + / −
- Movies and Series: groups, posters, seasons / episodes, resume where it stopped

## What only the owner can do
1. A free Samsung account → https://seller.samsungapps.com (Seller Office) for the store, and Tizen Studio
   (https://developer.tizen.org) on the laptop.
2. In Tizen Studio: *Tools → Certificate Manager* → a **Samsung** certificate (it signs in with the Samsung account).
3. *File → Import → Tizen Project* → this folder → *Build Signed Package* → `SAUDI.TV.wgt`.
4. To try it on a TV: TV *Apps* → type 12345 → Developer mode ON + the laptop's IP → restart the TV → in Tizen
   Studio *Device Manager* connect to the TV → *Run As → Tizen Web Application*.
5. For the store: upload the `.wgt` in Seller Office. Samsung reviews every TV app (usually a few weeks) and can
   refuse players that open provider playlists.
