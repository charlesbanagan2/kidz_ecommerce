# Google OAuth Setup Guide

## 1. Create Google OAuth Application

1. **Go to Google Cloud Console**: https://console.cloud.google.com/
2. **Create a new project** or select existing one
3. **Enable Google+ API**:
   - Go to "APIs & Services" > "Library"
   - Search for "Google+ API" and enable it
4. **Create OAuth Credentials**:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client IDs"
   - Choose "Web application"
   - Name: "Ecommerce Web OAuth"
   - Set **Authorized redirect URIs**:
     ```
     http://127.0.0.1:5000/login/google/authorized
     http://localhost:5000/login/google/authorized
     ```

## 2. Update Application Configuration

In `app.py`, update these lines with your actual credentials:
```python
app.config['GOOGLE_OAUTH_CLIENT_ID'] = '668360708226-q79n83ttq956po4cj3pd5qig0thiqp6c.apps.googleusercontent.com'
app.config['GOOGLE_OAUTH_CLIENT_SECRET'] = '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' 
```

## 3. Local Development

For localhost development, Google OAuth will work with:
- **Client ID**: 668360708226-q79n83ttq956po4cj3pd5qig0thiqp6c.apps.googleusercontent.com
- **Client Secret**: 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
- **Redirect URIs**: 
  - `http://127.0.0.1:5000/login/google/authorized`
  - `http://localhost:5000/login/google/authorized`

## 4. How Google Login Works

1. **User clicks "Sign in with Google"**
2. **Redirected to Google** for authentication
3. **Google redirects back** with user info
4. **System checks** if user exists:
   - **If exists**: Logs them in
   - **If new**: Creates account with Google info
   - **If email exists**: Links Google account to existing account

## 5. User Experience

- **First time**: User creates account via Google instantly
- **Returning**: User logs in with one click
- **Profile completion**: Users with Google accounts still need to add phone/address

## 6. Security Notes

- **Email verification**: Not needed since Google already verified
- **No password**: Google users don't need local password
- **Account linking**: Existing users can link their Google account

## 7. Testing Without Google Setup

If you don't set up Google OAuth:
- **Comment out** the Google OAuth imports and routes
- **Remove** the Google login button from templates
- **Regular login** will still work perfectly

## 8. Production Deployment

For production, update:
- **Authorized redirect URI**: `https://yourdomain.com/login/google/authorized`
- **Use environment variables** for credentials
- **Enable HTTPS** for security
