# Browser Storage Export Guide

Fix authentication issues with hot-buzz.hot.net.il by copying your complete browser storage.

## Quick Fix (Recommended)

### Method 1: Browser Console Export (5 minutes)

1. **Open hot-buzz.hot.net.il in your logged-in browser**
2. **Open Developer Tools** (F12 or Cmd+Option+I)
3. **Go to Console tab**
4. **Run these commands one by one:**

```javascript
// Export LocalStorage
console.log("=== LOCALSTORAGE ===");
console.log(JSON.stringify(localStorage));

// Export SessionStorage  
console.log("=== SESSIONSTORAGE ===");
console.log(JSON.stringify(sessionStorage));

// Export Cookies
console.log("=== COOKIES ===");
console.log(document.cookie);
```

5. **Copy the output** and save to a text file
6. **Run the importer:**

```bash
# On Mac
python3 browser_storage_exporter.py --manual-json '{"localStorage":YOUR_LOCALSTORAGE_JSON,"sessionStorage":YOUR_SESSIONSTORAGE_JSON}' --proxy-base ~/Hot/infra/proxy/ssh_transfer

# On Windows
python browser_storage_exporter.py --manual-json "{\"localStorage\":YOUR_LOCALSTORAGE_JSON}" --proxy-base C:\WebServerTest\ssh_transfer
```

### Method 2: Automatic Browser Export

```bash
# Chrome (auto-detect profile)
python browser_storage_exporter.py --browser chrome --domain hot-buzz.hot.net.il

# Firefox (auto-detect profile)  
python browser_storage_exporter.py --browser firefox --domain hot-buzz.hot.net.il

# Custom profile path
python browser_storage_exporter.py --profile-path "/path/to/browser/profile" --browser chrome
```

## What Gets Exported

✅ **Cookies** - Authentication tokens, session IDs  
✅ **LocalStorage** - Persistent app data, tokens  
✅ **SessionStorage** - Temporary session data  
✅ **IndexedDB** - Complex application data  
✅ **Browser Cache** - Cached responses  

## Common Authentication Storage

For hot-buzz.hot.net.il, look for these storage items:

**Cookies:**
- `session_id`
- `auth_token` 
- `login_token`
- `JSESSIONID`
- `PHPSESSID`

**LocalStorage:**
- `authToken`
- `userSession`
- `loginData`
- `jwt_token`

## Troubleshooting

### Issue: "No browser profiles found"
**Solution:** Use manual export method above

### Issue: "Permission denied accessing browser database"
**Solution:** Close browser completely before running export

### Issue: "Still getting blank page after import"
**Solution:** 
1. Check you're using the correct domain: `hot-buzz.hot.net.il`
2. Make sure you copied ALL storage types
3. Try exporting from an incognito/private window session

### Issue: "JSON parse error"
**Solution:** 
1. Make sure to copy the complete JSON output
2. Escape quotes properly: `\"` instead of `"`
3. Use single quotes around the JSON string

## Advanced Usage

### Export All Storage Types
```bash
python browser_storage_exporter.py --browser chrome --export-file my_auth_storage.json
```

### Import Existing Export
```bash
python browser_storage_exporter.py --import-file my_auth_storage.json --proxy-base C:\WebServerTest\ssh_transfer
```

### Check What Was Imported
```bash
# Windows
type C:\WebServerTest\ssh_transfer\cache\cookies.json

# Mac  
cat ~/Hot/infra/proxy/ssh_transfer/cache/cookies.json
```

## Testing After Import

1. **Restart the proxy system**
2. **Configure browser to use proxy** (localhost:8000)
3. **Navigate to hot-buzz.hot.net.il/login**
4. **Should see authenticated content instead of blank page**

## Security Note

The exported storage contains sensitive authentication data. Keep the export files secure and delete them after importing to the proxy system.

## Quick Commands Summary

```bash
# 1. Export browser storage
python browser_storage_exporter.py --browser chrome

# 2. Restart proxy (Mac)
python3 ssh_proxy_mac_raw.py

# 3. Restart proxy (Windows) 
python ssh_raw_transfer_windows.py --mac-host YOUR_MAC_IP --mac-user YOUR_USERNAME

# 4. Test in browser with proxy configured
```