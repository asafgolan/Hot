connect to adb brigde and streamer to tv
nvigate to chrome://inspect/#pages

if the app is in debug webview enabled we can get the webview html content if not we need to enable it if not 

adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml ~/Hot/ui.xml- in order to dump the app

get streamer model
adb -s 192.168.1.10:32869 shell getprop ro.product.model

 adb -s 192.168.1.10:32869 shell settings put global webview_debug_enabled 1

 adb -s 192.168.1.10:32869 shell settings put global webview_provider com.google.android.webview


 #restart the app
 #kill
adb -s 192.168.1.10:32869 shell am force-stop il.net.hot.hot
#start
adb -s 192.168.1.10:32869 shell am start -n il.net.hot.hot/il.net.hot.hot.TvMainActivity


adb -s 192.168.1.10:32869 shell am start -n il.net.hot.hot/il.net.hot.hot.TvMainActivity