# DAILYWINS Updated Website Files

## Included changes
- Updated `index.html` with the supplied `DW4.png` image as the hero background.
- Added a white logo treatment and a white highlight treatment for the main hero heading.
- Added a continuously scrolling crypto market ticker.
- The ticker fetches BTC, ETH, SOL, XRP, BNB, ADA and DOGE prices and 24-hour changes from CoinGecko at runtime, refreshing every 60 seconds.
- Added `register.html` to match the existing login and account flow.
- Preserved the uploaded templates and copied them into the `templates/` folder.
- Added `DW3.png`, `DW4.png`, and `logo.png` into `static/images/`.

## Expected Flask structure
Place this project folder beside your Flask app so that:
- HTML files are in `templates/`
- Images are in `static/images/`

The existing Jinja/Flask `url_for(...)` references were preserved.
