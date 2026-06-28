tell application "Terminal"
	activate
	do script "cd ~/Vibecode/fba-backend && git add backend/scrapers/dataforseo_reviews.py && git commit -m 'fix: extract numeric rating value from DataForSEO dict response' && git push && echo '✅ Done! Railway will auto-deploy in ~1 min.'"
end tell
