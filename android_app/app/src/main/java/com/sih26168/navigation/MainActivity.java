package com.sih26168.navigation;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.webkit.GeolocationPermissions;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    private static final int LOCATION_REQUEST = 42;
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setBuiltInZoomControls(false);
        settings.setMediaPlaybackRequiresUserGesture(false);

        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onGeolocationPermissionsShowPrompt(
                    String origin, GeolocationPermissions.Callback callback) {
                if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
                        == PackageManager.PERMISSION_GRANTED) {
                    callback.invoke(origin, true, false);
                } else {
                    pendingOrigin = origin;
                    pendingCallback = callback;
                    requestPermissions(
                            new String[]{Manifest.permission.ACCESS_FINE_LOCATION,
                                    Manifest.permission.ACCESS_COARSE_LOCATION},
                            LOCATION_REQUEST);
                }
            }
        });

        setContentView(webView);

        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(
                    new String[]{Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION},
                    LOCATION_REQUEST);
        } else {
            loadApp();
        }
    }

    private String pendingOrigin;
    private GeolocationPermissions.Callback pendingCallback;

    private void loadApp() {
        webView.loadUrl("file:///android_asset/web/index.html");
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == LOCATION_REQUEST) {
            if (pendingCallback != null) {
                boolean granted = grantResults.length > 0
                        && grantResults[0] == PackageManager.PERMISSION_GRANTED;
                pendingCallback.invoke(pendingOrigin, granted, false);
                pendingCallback = null;
                pendingOrigin = null;
            }
            loadApp();
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }
}
