package com.voiceguard.android;

import android.telecom.Call;
import android.telecom.InCallService;
import android.content.Intent;

public class VoiceGuardInCallService extends InCallService {
    @Override public void onCallAdded(Call call){ super.onCallAdded(call); call.registerCallback(new Call.Callback(){
        @Override public void onStateChanged(Call c,int state){ if(state==Call.STATE_ACTIVE) start(); else if(state==Call.STATE_DISCONNECTED) stop(); }
    }); if(call.getState()==Call.STATE_ACTIVE) start(); }
    @Override public void onCallRemoved(Call call){ super.onCallRemoved(call); stop(); }
    private void start(){ try{startForegroundService(new Intent(this,VoiceMonitorService.class));}catch(Exception ignored){} }
    private void stop(){ try{stopService(new Intent(this,VoiceMonitorService.class));}catch(Exception ignored){} }
}
