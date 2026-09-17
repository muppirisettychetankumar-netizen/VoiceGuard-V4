package com.voiceguard.android;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.media.*;
import android.os.*;
import androidx.core.app.NotificationCompat;
import okhttp3.*;
import okio.ByteString;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.TimeUnit;

public class VoiceMonitorService extends Service {
    static final int NOTIF=2614; volatile boolean running=false; AudioRecord recorder; Thread worker; WebSocket ws; OkHttpClient client;
    @Override public void onCreate(){super.onCreate(); createChannel(); startForeground(NOTIF, notification("Preparing voice protection…"));}
    @Override public int onStartCommand(Intent i,int flags,int id){ if(!running) startMonitor(); return START_NOT_STICKY; }
    void startMonitor(){
        if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED){stopSelf();return;}
        String base=getSharedPreferences("vg",0).getString("url","").trim(); if(base.isEmpty()){stopSelf();return;}
        String wsUrl=base.replaceFirst("^http://","ws://").replaceFirst("^https://","wss://"); if(!wsUrl.endsWith("/ws/live")) wsUrl=wsUrl.replaceAll("/+$","")+"/ws/live";
        client=new OkHttpClient.Builder().readTimeout(0,TimeUnit.MILLISECONDS).build();
        Request req=new Request.Builder().url(wsUrl).build();
        ws=client.newWebSocket(req,new WebSocketListener(){@Override public void onOpen(WebSocket w,Response r){w.send("{\"type\":\"config\",\"sampleRate\":16000,\"source\":\"android-call-monitor\"}"); update("VoiceGuard is monitoring live audio");}
            @Override public void onMessage(WebSocket w,String text){update("Detection: "+text);}
            @Override public void onFailure(WebSocket w,Throwable t,Response r){update("Engine connection failed: "+t.getMessage());}
        });
        int sr=16000; int min=AudioRecord.getMinBufferSize(sr,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT); int size=Math.max(min*2,4096);
        try{recorder=new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION,sr,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,size);}catch(Exception e){try{recorder=new AudioRecord(MediaRecorder.AudioSource.MIC,sr,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,size);}catch(Exception x){stopSelf();return;}}
        recorder.startRecording(); running=true;
        worker=new Thread(()->{short[] b=new short[2048]; while(running){int n=recorder.read(b,0,b.length,AudioRecord.READ_BLOCKING); if(n>0 && ws!=null){ByteBuffer bb=ByteBuffer.allocate(n*2).order(ByteOrder.LITTLE_ENDIAN);for(int k=0;k<n;k++)bb.putShort(b[k]);ws.send(ByteString.of(bb.array()));}}},"VoiceGuardAudio"); worker.start();
    }
    @Override public void onDestroy(){running=false;try{if(recorder!=null){recorder.stop();recorder.release();}}catch(Exception ignored){} if(ws!=null)ws.close(1000,"service stopped",null);if(client!=null)client.dispatcher().executorService().shutdown();super.onDestroy();}
    @Override public android.os.IBinder onBind(Intent i){return null;}
    void createChannel(){if(Build.VERSION.SDK_INT>=26){NotificationManager nm=getSystemService(NotificationManager.class);nm.createNotificationChannel(new NotificationChannel("voiceguard","VoiceGuard protection",NotificationManager.IMPORTANCE_LOW));}}
    Notification notification(String s){return new NotificationCompat.Builder(this,"voiceguard").setSmallIcon(android.R.drawable.ic_lock_silent_mode_off).setContentTitle("VoiceGuard").setContentText(s).setOngoing(true).setCategory(NotificationCompat.CATEGORY_SERVICE).build();}
    void update(String s){NotificationManager nm=getSystemService(NotificationManager.class);nm.notify(NOTIF,notification(s));}
}
