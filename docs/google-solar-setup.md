# Connect Google Solar

Step 3 local filters work now. Live roof and existing-solar checks need your Google Cloud project. No paid Google calls have been made during this implementation.

## Setup

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. Link a billing account and enable **Solar API** for that project.
3. Create an API key under **APIs & Services → Credentials**. Restrict it to **Solar API**. This is a server key; use server/public-IP restrictions rather than browser-referrer restrictions. Local development uses your network's public outbound IP, not 127.0.0.1.
4. In the project's local `.env` file, add `GOOGLE_SOLAR_API_KEY=YOUR_KEY`. Never put the key in frontend code, a `VITE_` variable, chat, or a tracked file.
5. Restart the local app with the existing `scripts/dev.py` launcher. Open a neighborhood → **Filters** → **Check solar data**.

Each click checks up to ten uncached, non-excluded homes. Click **Check next homes** to continue. Previewing and saving reports do not make Google requests. Use Google Cloud quotas to control spending; budget alerts alone do not impose a spending cap.

## Results

- **Arrays detected:** existing solar; excluded when that filter is enabled.
- **No arrays detected:** no solar observed at the supplied capture date. The app shows that date; later installations are possible.
- **Not checked:** no lookup yet; remains selected.
- **Unavailable / failed / building mismatch:** affected home needs review. A nearest-building response outside the intended parcel is rejected.
- Roof area and potential capacity feed optional thresholds. Potential capacity is not a completed design or a usage-sized system.

Live detection is not verified until the first successful request with your project. Tests use synthetic responses, never pretend fixtures are live Google results.

## Retention and display

Solar content is cached for at most 30 days. Saved filter reports containing Solar content expire at the earliest contributing cache expiry; local-only reports remain unchanged. Expired Solar rows/reports are removed at startup, hourly while the app runs, and report read/save paths. Stopped local apps clean expired content when restarted. Failed network checks can be retried after five minutes.

Google-derived results appear in the filter sheet with attribution. They are not drawn on the current non-Google map. Rental styling uses local assessor data.

Sources: [Google setup](https://developers.google.com/maps/documentation/solar/get-api-key), [Solar API reference](https://developers.google.com/maps/documentation/solar/reference/rest/v1/buildingInsights/findClosest), [Google Solar policies](https://developers.google.com/maps/documentation/solar/policies), [Solar-specific terms](https://cloud.google.com/maps-platform/terms/maps-service-terms#20.-solar-api).
