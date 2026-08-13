# Meeting Attendance Scanner

A mobile-friendly web app for scanning participant name-tag QR codes to confirm
attendance across one or more meeting days. Works entirely from a phone's
browser — no app-store install needed.

## Why a web app instead of a native Python app?

Packaging real Python code into an installable Android/iOS app (e.g. with
Kivy + Buildozer) is slow to build, fragile, and Apple won't allow
Python-interpreter apps on iOS at all. A web app gives you the same result —
a phone camera scanning QR codes, working over the internet or your local
WiFi — and opens instantly with just a link, on any phone.

## What it does

- **Create a meeting** with a start and end date (1 day, 2 days, 5 days — any
  range). The app automatically works out every calendar day in between.
- **Add participants** to a meeting. Each one gets a unique QR code.
- **Print name tags** (single or all at once) with the QR code embedded.
- **Scan page**: pick which day you're checking people in for, then scan tags
  with the phone camera. Each scan instantly logs the person as present for
  that specific day, with duplicate-scan protection.
- **Report**: a matrix showing every participant against every day of the
  meeting, with a ✓ for each day they attended, plus a CSV export.

## 1. Install

```bash
pip install -r requirements.txt
```

## 2. Run

```bash
python app.py
```

This starts the server on port 5000 with a self-signed HTTPS certificate.
Mobile browsers require HTTPS (or `localhost`) before they'll allow a page to
use the camera, which is why `ssl_context="adhoc"` is turned on in `app.py`.

You'll see something like:

```
* Running on https://127.0.0.1:5000
* Running on https://<your-computer's-LAN-IP>:5000
```

## 3. Access it

- **From the same computer**: open `https://127.0.0.1:5000`
- **From a phone on the same WiFi**: find your computer's LAN IP address
  (e.g. `192.168.1.24` — on Windows run `ipconfig`, on Mac/Linux run
  `ifconfig` or `ip addr`) and open `https://192.168.1.24:5000` on the phone.
  The browser will warn that the certificate isn't trusted (because it's
  self-signed) — tap **Advanced → Proceed anyway**. This is safe for local
  network use.
- **For scanning from anywhere / a real deployment**: deploy the app to any
  host that gives you a proper HTTPS domain (Render, Railway, PythonAnywhere,
  a VPS with a Let's Encrypt certificate, etc.), or tunnel it during an event
  with a tool like `ngrok` (`ngrok http 5000`), which gives you a trusted
  `https://...ngrok.io` link to open on the scanning phone.

## 4. Typical workflow for an event

1. Create the meeting with its date range.
2. Add all participants (name + organization). Each gets a QR code
   automatically.
3. Click **Print All Badges** and print/cut the name tags before the event.
4. On the day of the meeting, open the **Scan** page on your phone, select
   today's date from the dropdown, and start scanning tags as people arrive.
5. If it's a multi-day meeting, just switch the date dropdown each morning —
   the same tags work for every day.
6. Open **Report** any time to see who attended which days, and export to
   CSV for your records.

## Data storage

Everything is stored locally in a SQLite file (`attendance.db`) that's
created automatically the first time you run the app. No external services
are required, and no data is sent anywhere outside your own server.

## Extending it

Next steps for the program:
- Multiple staff members scanning at once.
- Email/SMS confirmation on check-in.
- adding attendee role(presenter/attendee) on tag
- adding organiser on Tag, for people who organized the meeting
- removing meeting name on Tag