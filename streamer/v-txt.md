

----------------------
# Background

1. open app as logged in user -> 
2. click chanell 999 - take screen shot assert valid
3. click home (move app bg)

# Steps

4. reopen app -> click O.k hot should be selected) ("17:10:55.709   711 21132 I ActivityTaskManager: START u0 {flg=0x10000000 cmp=il.net.hot.hot/.TvMainActivity} with LAUNCH_SINGLE_TASK from uid 2000 (BAL_ALLOW_PERMISSION) result code=0"

5. init loader (timetrace) point APP START 
5.1. seconed loader (time trace)
BELOW->
```bash 

    # Validate 5 + 5.1

    DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell:  try handler com.android.wm.shell.transition.DefaultTransitionHandler@c819549
    DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell: start default transition animation, info = {id=276 t=OPEN f=0x0 trk=0 r=[0@Point(0, 0)] c=[{WCT{android.window.IWindowContainerToken$Stub$Proxy@1b51fc} m=OPEN f=NONE leash=Surface(name=Task=174)/@0x5a600c9 sb=Rect(0, 0 - 1920, 1080) eb=Rect(0, 0 - 1920, 1080) d=0},{WCT{android.window.IWindowContainerToken$Stub$Proxy@384e085} m=TO_BACK f=NONE leash=Surface(name=Task=1)/@0x61c3ce sb=Rect(0, 0 - 1920, 1080) eb=Rect(0, 0 - 1920, 1080) d=0}]}
    DEBUG LOG V: 06-22 17:10:56.666  1030  1075 V WindowManagerShell: loadAnimation: anim=android.view.animation.AlphaAnimation@9c991e8 animAttr=0x9 type=OPEN isEntrance=false
    DEBUG LOG V: 06-22 17:10:56.666  1030  1075 V WindowManagerShell: loadAnimation: anim=android.view.animation.AlphaAnimation@e1e7ea6 animAttr=0x8 type=OPEN isEntrance=true
    DEBUG LOG V: 06-22 17:10:56.668  1030  1075 V WindowManagerShell:  animated by com.android.wm.shell.transition.DefaultTransitionHandler@c819549
```

5.2. Validate  Mosaicis  live selection with (big brother focused) - Oleg to assert UI elm  ?

- neptune - ? 
- android UI elm


----------------------


hot-e2e) asafgolan@asafs-MacBook-Pro streamer % /opt/homebrew/Caskroom/miniforge/base/envs/hot-e2e/bin/python test_hot_app_launch.py
Results will be saved to: /Users/asafgolan/Hot/streamer/test_results/run_20250622_071053
Clearing Android logs before starting test...
Starting log monitoring...
Launching HOT app...
DEBUG LOG I: 06-22 17:10:55.709   711 21132 I ActivityTaskManager: START u0 {flg=0x10000000 cmp=il.net.hot.hot/.TvMainActivity} with LAUNCH_SINGLE_TASK from uid 2000 (BAL_ALLOW_PERMISSION) result code=0
DEBUG LOG V: 06-22 17:10:55.710  1030  1075 V WindowManagerShell: Transition requested: android.os.BinderProxy@8401182 TransitionRequestInfo { type = OPEN, triggerTask = TaskInfo{userId=0 taskId=174 displayId=0 isRunning=true baseIntent=Intent { flg=0x10000000 cmp=il.net.hot.hot/.TvMainActivity } baseActivity=ComponentInfo{il.net.hot.hot/il.net.hot.hot.TvMainActivity} topActivity=ComponentInfo{il.net.hot.hot/il.net.hot.hot.TvMainActivity} origActivity=null realActivity=ComponentInfo{il.net.hot.hot/il.net.hot.hot.TvMainActivity} numActivities=1 lastActiveTime=30728517 supportsMultiWindow=false resizeMode=1 isResizeable=true minWidth=-1 minHeight=-1 defaultMinSize=220 token=WCT{android.window.IWindowContainerToken$Stub$Proxy@5294093} topActivityType=1 pictureInPictureParams=null shouldDockBigOverlays=true launchIntoPipHostTaskId=-1 lastParentTaskIdBeforePip=-1 displayCutoutSafeInsets=null topActivityInfo=ActivityInfo{8ef78d0 il.net.hot.hot.TvMainActivity} launchCookies=[] positionInParent=Point(0, 0) parentTaskId=-1 isFocused=false isVisible=false isVisibleRequested=false isSleeping=false topActivityInSizeCompat=false topActivityEligibleForLetterboxEducation= false topActivityLetterboxed= false isFromDoubleTap= false topActivityLetterboxVerticalPosition= -1 topActivityLetterboxHorizontalPosition= -1 topActivityLetterboxWidth=-1 topActivityLetterboxHeight=-1 locusId=null displayAreaFeatureId=1 cameraCompatControlState=hidden}, remoteTransition = null, displayChange = null }
Launch command output: Starting: Intent { cmp=il.net.hot.hot/.TvMainActivity }

DEBUG LOG I: 06-22 17:10:56.566   711   850 I ActivityManager: Start proc 29499:com.google.android.webview:sandboxed_process0:org.chromium.content.app.SandboxedProcessService0:1/u0i75 for  {il.net.hot.hot/org.chromium.content.app.SandboxedProcessService0:1}
DEBUG LOG I: 06-22 17:10:56.614   711 21132 I ActivityManager: Flag disabled. Ignoring finishAttachApplication from uid: 99075. pid: 29499
DEBUG LOG V: 06-22 17:10:56.664  1030  1075 V WindowManagerShell: onTransitionReady android.os.BinderProxy@8401182: {id=276 t=OPEN f=0x0 trk=0 r=[0@Point(0, 0)] c=[{WCT{android.window.IWindowContainerToken$Stub$Proxy@1b51fc} m=OPEN f=NONE leash=Surface(name=Task=174)/@0x5a600c9 sb=Rect(0, 0 - 1920, 1080) eb=Rect(0, 0 - 1920, 1080) d=0},{WCT{android.window.IWindowContainerToken$Stub$Proxy@384e085} m=TO_BACK f=NONE leash=Surface(name=Task=1)/@0x61c3ce sb=Rect(0, 0 - 1920, 1080) eb=Rect(0, 0 - 1920, 1080) d=0}]}
DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell: Playing animation for (#276)android.os.BinderProxy@8401182@0
DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell:  try handler com.android.wm.shell.keyguard.KeyguardTransitionHandler@e76314d
DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell:  try handler com.android.wm.shell.activityembedding.ActivityEmbeddingController@9e6a402
DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell:  try handler com.android.wm.shell.pip.tv.TvPipTransition@8b8a113
DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell:  try handler com.android.wm.shell.transition.RemoteTransitionHandler@f628f50
DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell: Transition doesn't have explicit remote, search filters for match for {id=276 t=OPEN f=0x0 trk=0 r=[0@Point(0, 0)] c=[{WCT{android.window.IWindowContainerToken$Stub$Proxy@1b51fc} m=OPEN f=NONE leash=Surface(name=Task=174)/@0x5a600c9 sb=Rect(0, 0 - 1920, 1080) eb=Rect(0, 0 - 1920, 1080) d=0},{WCT{android.window.IWindowContainerToken$Stub$Proxy@384e085} m=TO_BACK f=NONE leash=Surface(name=Task=1)/@0x61c3ce sb=Rect(0, 0 - 1920, 1080) eb=Rect(0, 0 - 1920, 1080) d=0}]}
DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell:  Delegate animation for #276 to null
DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell:  try handler com.android.wm.shell.transition.DefaultTransitionHandler@c819549
DEBUG LOG V: 06-22 17:10:56.665  1030  1075 V WindowManagerShell: start default transition animation, info = {id=276 t=OPEN f=0x0 trk=0 r=[0@Point(0, 0)] c=[{WCT{android.window.IWindowContainerToken$Stub$Proxy@1b51fc} m=OPEN f=NONE leash=Surface(name=Task=174)/@0x5a600c9 sb=Rect(0, 0 - 1920, 1080) eb=Rect(0, 0 - 1920, 1080) d=0},{WCT{android.window.IWindowContainerToken$Stub$Proxy@384e085} m=TO_BACK f=NONE leash=Surface(name=Task=1)/@0x61c3ce sb=Rect(0, 0 - 1920, 1080) eb=Rect(0, 0 - 1920, 1080) d=0}]}
DEBUG LOG V: 06-22 17:10:56.666  1030  1075 V WindowManagerShell: loadAnimation: anim=android.view.animation.AlphaAnimation@9c991e8 animAttr=0x9 type=OPEN isEntrance=false
DEBUG LOG V: 06-22 17:10:56.666  1030  1075 V WindowManagerShell: loadAnimation: anim=android.view.animation.AlphaAnimation@e1e7ea6 animAttr=0x8 type=OPEN isEntrance=true
DEBUG LOG V: 06-22 17:10:56.668  1030  1075 V WindowManagerShell:  animated by com.android.wm.shell.transition.DefaultTransitionHandler@c819549
DEBUG LOG I: 06-22 17:10:56.703   711   839 I ActivityTaskManager: Displayed il.net.hot.hot/.TvMainActivity for user 0: +960ms
Recovered log line (with replacements): 06-22 17:10:57.007   618 29539 D Codec2-OutputBufferQueue: set max dequeue count 22 from update
DEBUG LOG V: 06-22 17:10:57.085  1030  1075 V WindowManagerShell: Transition animation finished (aborted=false), notifying core (#276)android.os.BinderProxy@8401182@0
DEBUG LOG V: 06-22 17:10:57.109  1030  1075 V WindowManagerShell: Track 0 became idle
DEBUG LOG V: 06-22 17:10:57.109  1030  1075 V WindowManagerShell: All active transition animations finished
Recovered log line (with replacements): 06-22 17:11:05.311   551  2717 D audioserver: FGS Logger Transaction failed