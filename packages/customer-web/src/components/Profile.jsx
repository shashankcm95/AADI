import React, { useState, useEffect, useRef } from 'react';
import { getUserProfile, updateUserProfile, getAvatarUploadUrl, uploadAvatarToS3 } from '../services/api';
import { isSafeUrl } from '../utils';

export default function Profile({ user, signOut }) {
    const [profile, setProfile] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [editing, setEditing] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [statusMessage, setStatusMessage] = useState(null);

    const [editName, setEditName] = useState('');
    const [editPhone, setEditPhone] = useState('');

    const fileInputRef = useRef(null);

    useEffect(() => {
        loadProfile();
    }, []);

    const loadProfile = async () => {
        try {
            const data = await getUserProfile();
            setProfile(data);
            setEditName(data.name || '');
            setEditPhone(data.phone_number || '');
        } catch (err) {
            console.error('Failed to load profile', err);
            setError('Failed to load profile. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        if (saving) return;
        setSaving(true);
        try {
            const updated = await updateUserProfile({
                name: editName,
                phone_number: editPhone
            });
            setProfile(updated);
            setEditing(false);
            setStatusMessage({ type: 'success', text: 'Profile updated!' });
        } catch (err) {
            setStatusMessage({ type: 'error', text: 'Failed to update profile' });
            console.error('Failed to update profile', err);
        } finally {
            setSaving(false);
        }
    };

    const handleFileSelect = async (e) => {
        if (e.target.files && e.target.files[0]) {
            const file = e.target.files[0];
            await uploadImage(file);
        }
    };

    const uploadImage = async (file) => {
        setUploading(true);
        try {
            const contentType = file.type || 'image/jpeg';
            // 1. Get Presigned URL
            const { upload_url, s3_key } = await getAvatarUploadUrl(contentType);

            // 2. Upload to S3
            await uploadAvatarToS3(upload_url, file, contentType);

            // 3. Update profile with the canonical storage key.
            const updated = await updateUserProfile({ picture: s3_key });
            setProfile(updated);
            setStatusMessage({ type: 'success', text: 'Profile picture updated!' });
        } catch (err) {
            console.error('Upload failed', err);
            setStatusMessage({ type: 'error', text: 'Failed to upload image' });
        } finally {
            setUploading(false);
        }
    };

    if (loading && !profile) return <div className="p-4">Loading profile...</div>;

    if (error && !profile) {
        return (
            <div className="profile-container fade-in">
                <div className="profile-card" style={{ textAlign: 'center', padding: '2rem' }}>
                    <h3>Error</h3>
                    <p>{error}</p>
                    <button className="btn btn-primary" onClick={() => { setError(null); setLoading(true); loadProfile(); }}>Retry</button>
                </div>
            </div>
        );
    }

    return (
        <div className="profile-container fade-in">
            <div className="profile-card">
                {statusMessage && (
                    <div style={{ padding: '8px 12px', marginBottom: 12, borderRadius: 6, background: statusMessage.type === 'error' ? '#fce4ec' : '#e8f5e9', color: statusMessage.type === 'error' ? '#c62828' : '#2e7d32' }}>
                        {statusMessage.text}
                        <button onClick={() => setStatusMessage(null)} style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
                    </div>
                )}
                <div className="profile-header">
                    <div className="avatar-wrapper">
                        <img
                            src={
                                isSafeUrl(profile?.picture_url)
                                    ? profile.picture_url
                                    : (isSafeUrl(profile?.picture) ? profile.picture : '/logo_icon_stylized.png')
                            }
                            alt="Profile"
                            className="profile-avatar"
                        />
                        <button
                            className="avatar-edit-btn"
                            onClick={() => fileInputRef.current?.click()}
                            disabled={uploading || editing}
                        >
                            📷
                        </button>
                        <input
                            type="file"
                            ref={fileInputRef}
                            style={{ display: 'none' }}
                            accept="image/*"
                            onChange={handleFileSelect}
                        />
                        {uploading && <div className="upload-spinner"></div>}
                    </div>

                    {!editing ? (
                        <div className="profile-info">
                            <h2>{profile?.name || user?.username || 'Customer'}</h2>
                            <p className="profile-meta">{profile?.email}</p>
                            {profile?.phone_number && <p className="profile-meta">{profile.phone_number}</p>}
                            <button className="btn btn-outline" onClick={() => setEditing(true)}>Edit Profile</button>
                        </div>
                    ) : (
                        <div className="profile-edit-form">
                            <div className="form-group">
                                <label>Name</label>
                                <input
                                    type="text"
                                    value={editName}
                                    onChange={e => setEditName(e.target.value)}
                                    className="input-field"
                                />
                            </div>
                            <div className="form-group">
                                <label>Phone</label>
                                <input
                                    type="tel"
                                    value={editPhone}
                                    onChange={e => setEditPhone(e.target.value)}
                                    className="input-field"
                                />
                            </div>
                            <div className="button-group">
                                <button className="btn btn-secondary" onClick={() => {
                                    setEditing(false);
                                    setEditName(profile?.name || '');
                                    setEditPhone(profile?.phone_number || '');
                                }}>Cancel</button>
                                <button className="btn btn-primary" onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
                            </div>
                        </div>
                    )}
                </div>

                <div className="profile-actions">
                    <button onClick={signOut} className="btn btn-danger full-width">Sign Out</button>
                </div>
            </div>
        </div>
    );
}
