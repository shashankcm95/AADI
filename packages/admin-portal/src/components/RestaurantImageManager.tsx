import { ChangeEvent, CSSProperties, useEffect, useMemo, useState } from 'react';
import * as api from '../services/api';

type RestaurantImage = {
    key: string;
    url?: string;
};

interface RestaurantImageManagerProps {
    restaurantId: string;
    initialImageKeys?: string[];
    initialImageUrls?: string[];
    maxImages?: number;
    onKeysChange?: (keys: string[]) => void;
    onSaveKeys?: (keys: string[]) => Promise<void>;
}

const DEFAULT_MAX_IMAGES = 5;

function toInitialImages(
    keys: string[] | undefined,
    urls: string[] | undefined,
    maxImages: number,
): RestaurantImage[] {
    if (!Array.isArray(keys)) {
        return [];
    }

    return keys
        .filter((key) => typeof key === 'string' && key.trim().length > 0)
        .slice(0, maxImages)
        .map((key, index) => ({
            key,
            url: Array.isArray(urls) ? urls[index] : undefined,
        }));
}

function errorMessage(error: unknown): string {
    if (error instanceof Error && error.message) {
        return error.message;
    }
    return 'Could not upload image. Please try again.';
}

export default function RestaurantImageManager({
    restaurantId,
    initialImageKeys = [],
    initialImageUrls = [],
    maxImages = DEFAULT_MAX_IMAGES,
    onKeysChange,
    onSaveKeys,
}: RestaurantImageManagerProps) {
    const [images, setImages] = useState<RestaurantImage[]>(() => toInitialImages(initialImageKeys, initialImageUrls, maxImages));
    const [uploading, setUploading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const keysSignature = useMemo(() => initialImageKeys.join('|'), [initialImageKeys]);
    const urlsSignature = useMemo(() => initialImageUrls.join('|'), [initialImageUrls]);

    useEffect(() => {
        const nextImages = toInitialImages(initialImageKeys, initialImageUrls, maxImages);
        setImages(nextImages);
        setError('');
        setSuccess('');
    }, [restaurantId, keysSignature, urlsSignature, maxImages]);

    const currentKeys = useMemo(() => images.map((item) => item.key), [images]);
    const remainingSlots = Math.max(0, maxImages - images.length);

    function applyImages(next: RestaurantImage[]) {
        setImages(next);
        onKeysChange?.(next.map((item) => item.key));
    }

    async function uploadFile(file: File): Promise<RestaurantImage> {
        const uploadMeta = await api.getImageUploadUrl(
            restaurantId,
            file.name,
            file.type || 'image/jpeg',
        );
        const uploadResponse = await fetch(uploadMeta.upload_url, {
            method: 'PUT',
            headers: {
                'Content-Type': file.type || 'image/jpeg',
            },
            body: file,
        });

        if (!uploadResponse.ok) {
            throw new Error(`Upload failed for ${file.name}`);
        }

        return {
            key: uploadMeta.object_key,
            url: uploadMeta.preview_url,
        };
    }

    async function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
        const files = Array.from(event.target.files || []);
        event.target.value = '';

        if (files.length === 0) {
            return;
        }

        const selectedFiles = files.slice(0, remainingSlots);
        if (selectedFiles.length < files.length) {
            setError(`Only ${maxImages} images are allowed per restaurant.`);
        } else {
            setError('');
        }
        setSuccess('');
        setUploading(true);

        const uploaded: RestaurantImage[] = [];
        const failures: string[] = [];
        for (const file of selectedFiles) {
            try {
                const nextImage = await uploadFile(file);
                uploaded.push(nextImage);
            } catch (uploadError) {
                failures.push(file.name);
                console.error(`Failed to upload ${file.name}:`, uploadError);
            }
        }
        if (uploaded.length > 0) {
            const next = [...images, ...uploaded].slice(0, maxImages);
            applyImages(next);
        }
        if (failures.length > 0 && uploaded.length > 0) {
            setError(`Failed to upload: ${failures.join(', ')}`);
            setSuccess(`${uploaded.length} image${uploaded.length === 1 ? '' : 's'} succeeded.`);
        } else if (failures.length > 0) {
            setError(`Failed to upload: ${failures.join(', ')}`);
        } else if (uploaded.length > 0) {
            setSuccess(`${uploaded.length} image${uploaded.length === 1 ? '' : 's'} uploaded.`);
        }
        setUploading(false);
    }

    function removeImage(key: string) {
        setError('');
        setSuccess('');
        applyImages(images.filter((image) => image.key !== key));
    }

    async function persistImages() {
        if (!onSaveKeys) {
            return;
        }
        setSaving(true);
        setError('');
        setSuccess('');
        try {
            await onSaveKeys(currentKeys);
            setSuccess('Images saved.');
        } catch (saveError) {
            setError(errorMessage(saveError));
        } finally {
            setSaving(false);
        }
    }

    return (
        <div style={styles.container}>
            <div style={styles.titleRow}>
                <h3 style={styles.title}>Restaurant Images</h3>
                <span style={styles.counter}>{images.length}/{maxImages}</span>
            </div>

            <p style={styles.helper}>
                Upload up to {maxImages} images. The first image is used as the main card photo in customer apps.
            </p>

            {error ? <div style={styles.errorBanner}>{error}</div> : null}
            {success ? <div style={styles.successBanner}>{success}</div> : null}

            <div style={styles.grid}>
                {images.map((image, index) => (
                    <div key={`${image.key}-${index}`} style={styles.tile}>
                        {image.url ? (
                            <img src={image.url} alt={`Restaurant ${index + 1}`} style={styles.preview} />
                        ) : (
                            <div style={styles.previewFallback}>Image {index + 1}</div>
                        )}
                        <div style={styles.tileFooter}>
                            <span style={styles.tileLabel}>Image {index + 1}</span>
                            <button
                                type="button"
                                onClick={() => removeImage(image.key)}
                                style={styles.removeButton}
                            >
                                Remove
                            </button>
                        </div>
                    </div>
                ))}
                {images.length === 0 ? (
                    <div style={styles.emptyTile}>
                        No images uploaded yet.
                    </div>
                ) : null}
            </div>

            <div style={styles.actions}>
                <label style={remainingSlots === 0 || uploading ? styles.uploadButtonDisabled : styles.uploadButton}>
                    {uploading ? 'Uploading...' : remainingSlots === 0 ? 'Image limit reached' : 'Upload Images'}
                    <input
                        type="file"
                        accept="image/*"
                        multiple
                        disabled={remainingSlots === 0 || uploading}
                        style={styles.hiddenInput}
                        onChange={handleFileSelection}
                    />
                </label>

                {onSaveKeys ? (
                    <button
                        type="button"
                        onClick={persistImages}
                        disabled={saving || uploading}
                        style={saving || uploading ? styles.saveButtonDisabled : styles.saveButton}
                    >
                        {saving ? 'Saving...' : 'Save Images'}
                    </button>
                ) : null}
            </div>
        </div>
    );
}

const styles: Record<string, CSSProperties> = {
    container: {
        border: '1px solid #dbeafe',
        borderRadius: 12,
        padding: '1rem',
        background: 'linear-gradient(135deg, rgba(104,177,193,0.08), rgba(75,153,186,0.02))',
        marginBottom: '1rem',
    },
    titleRow: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '0.5rem',
    },
    title: {
        margin: 0,
        color: '#2162BA',
        fontSize: '1rem',
    },
    counter: {
        fontSize: '0.85rem',
        color: '#546E7A',
    },
    helper: {
        marginTop: '0.5rem',
        marginBottom: '0.75rem',
        color: '#546E7A',
        fontSize: '0.85rem',
    },
    errorBanner: {
        background: '#fee2e2',
        border: '1px solid #fecaca',
        color: '#b91c1c',
        borderRadius: 8,
        padding: '0.5rem 0.75rem',
        marginBottom: '0.75rem',
    },
    successBanner: {
        background: '#dcfce7',
        border: '1px solid #bbf7d0',
        color: '#166534',
        borderRadius: 8,
        padding: '0.5rem 0.75rem',
        marginBottom: '0.75rem',
    },
    grid: {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
        gap: '0.75rem',
    },
    tile: {
        border: '1px solid #dbeafe',
        borderRadius: 10,
        overflow: 'hidden',
        background: '#fff',
    },
    preview: {
        width: '100%',
        height: 110,
        objectFit: 'cover',
        display: 'block',
    },
    previewFallback: {
        width: '100%',
        height: 110,
        background: 'linear-gradient(135deg, rgba(115,195,197,0.2), rgba(33,98,186,0.2))',
        color: '#2162BA',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontWeight: 600,
    },
    tileFooter: {
        padding: '0.5rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '0.5rem',
    },
    tileLabel: {
        color: '#546E7A',
        fontSize: '0.8rem',
    },
    removeButton: {
        border: 'none',
        background: 'transparent',
        color: '#b91c1c',
        cursor: 'pointer',
        fontSize: '0.8rem',
        fontWeight: 600,
    },
    emptyTile: {
        border: '1px dashed #bfdbfe',
        borderRadius: 10,
        minHeight: 110,
        color: '#546E7A',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0.75rem',
        textAlign: 'center',
        background: 'rgba(255,255,255,0.75)',
    },
    actions: {
        marginTop: '0.85rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
    },
    uploadButton: {
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: 8,
        padding: '0.55rem 0.9rem',
        border: '1px solid rgba(33,98,186,0.2)',
        background: '#FEFEFE',
        color: '#2162BA',
        cursor: 'pointer',
        fontWeight: 600,
        fontSize: '0.9rem',
    },
    uploadButtonDisabled: {
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: 8,
        padding: '0.55rem 0.9rem',
        border: '1px solid #cbd5e1',
        background: '#f8fafc',
        color: '#94a3b8',
        cursor: 'not-allowed',
        fontWeight: 600,
        fontSize: '0.9rem',
    },
    saveButton: {
        borderRadius: 8,
        padding: '0.55rem 0.9rem',
        border: 'none',
        background: 'linear-gradient(135deg, #73C3C5, #2162BA)',
        color: '#fff',
        cursor: 'pointer',
        fontWeight: 700,
        fontSize: '0.9rem',
    },
    saveButtonDisabled: {
        borderRadius: 8,
        padding: '0.55rem 0.9rem',
        border: 'none',
        background: '#94a3b8',
        color: '#fff',
        cursor: 'not-allowed',
        fontWeight: 700,
        fontSize: '0.9rem',
    },
    hiddenInput: {
        display: 'none',
    },
};
