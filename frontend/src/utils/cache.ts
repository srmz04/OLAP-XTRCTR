/**
 * SmartCache - 3-Tier Cache with Validation and Fallback
 * 
 * Architecture:
 * L1 (Memory)    → Instant, session-only
 * L2 (localStorage) → Fast (5ms), persistent across sessions
 * L3 (Gist)      → Slow (200ms), shared across devices
 * 
 * Features:
 * - Automatic tier promotion (Gist → localStorage → memory)
 * - Checksum validation
 * - TTL management
 * - Fallback to server on cache miss
 */

interface CacheEntry<T> {
    data: T;
    timestamp: number;
    checksum: string;
    ttl: number; // milliseconds, 0 = never expires
}

interface CacheConfig {
    gistId: string;
    gistToken: string;
    defaultTTL: number; // 7 days default
}

// Simple hash for checksum
function simpleHash(str: string): string {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32bit integer
    }
    return Math.abs(hash).toString(16).padStart(8, '0');
}

class SmartCache {
    private memory: Map<string, CacheEntry<unknown>> = new Map();
    private config: CacheConfig;
    private gistFilesCache: Map<string, unknown> | null = null;

    constructor(config: Partial<CacheConfig> = {}) {
        this.config = {
            gistId: config.gistId || import.meta.env.VITE_GIST_ID || '',
            gistToken: config.gistToken || import.meta.env.VITE_GITHUB_TOKEN || '',
            defaultTTL: config.defaultTTL || 7 * 24 * 60 * 60 * 1000, // 7 days
        };
    }

    /**
     * Get data with 3-tier fallback
     */
    async get<T>(key: string): Promise<T | null> {
        // L1: Memory (instant)
        const memoryEntry = this.memory.get(key) as CacheEntry<T> | undefined;
        if (memoryEntry && this.isValid(memoryEntry)) {
            console.log(`[Cache L1] HIT: ${key}`);
            return memoryEntry.data;
        }

        // L2: localStorage (fast)
        const localEntry = this.getFromLocalStorage<T>(key);
        if (localEntry && this.isValid(localEntry)) {
            console.log(`[Cache L2] HIT: ${key}`);
            // Promote to L1
            this.memory.set(key, localEntry);
            return localEntry.data;
        }

        // L3: Gist (slow)
        const gistEntry = await this.getFromGist<T>(key);
        if (gistEntry && this.isValid(gistEntry)) {
            console.log(`[Cache L3] HIT: ${key}`);
            // Promote to L2 and L1
            this.saveToLocalStorage(key, gistEntry);
            this.memory.set(key, gistEntry);
            return gistEntry.data;
        }

        console.log(`[Cache] MISS: ${key}`);
        return null;
    }

    /**
     * Save data to all cache tiers
     */
    async set<T>(key: string, data: T, ttl?: number): Promise<void> {
        const entry: CacheEntry<T> = {
            data,
            timestamp: Date.now(),
            checksum: simpleHash(JSON.stringify(data)),
            ttl: ttl ?? this.config.defaultTTL,
        };

        // Save to all tiers
        this.memory.set(key, entry);
        this.saveToLocalStorage(key, entry);
        await this.saveToGist(key, entry);

        console.log(`[Cache] SET: ${key} (checksum: ${entry.checksum})`);
    }

    /**
     * Check if entry is valid (not expired, checksum OK)
     */
    private isValid<T>(entry: CacheEntry<T>): boolean {
        // Check TTL
        if (entry.ttl > 0) {
            const age = Date.now() - entry.timestamp;
            if (age > entry.ttl) {
                console.log(`[Cache] EXPIRED: age=${age}ms, ttl=${entry.ttl}ms`);
                return false;
            }
        }

        // Validate checksum
        const currentChecksum = simpleHash(JSON.stringify(entry.data));
        if (currentChecksum !== entry.checksum) {
            console.log(`[Cache] CHECKSUM MISMATCH: expected=${entry.checksum}, got=${currentChecksum}`);
            return false;
        }

        return true;
    }

    // === L2: localStorage ===

    private getFromLocalStorage<T>(key: string): CacheEntry<T> | null {
        try {
            const raw = localStorage.getItem(`olapxtrctr_${key}`);
            if (!raw) return null;
            return JSON.parse(raw) as CacheEntry<T>;
        } catch {
            return null;
        }
    }

    private saveToLocalStorage<T>(key: string, entry: CacheEntry<T>): void {
        try {
            localStorage.setItem(`olapxtrctr_${key}`, JSON.stringify(entry));
        } catch (e) {
            console.warn(`[Cache L2] Storage full, skipping: ${key}`, e);
        }
    }

    // === L3: Gist ===

    private async getFromGist<T>(key: string): Promise<CacheEntry<T> | null> {
        if (!this.config.gistId || !this.config.gistToken) {
            return null;
        }

        try {
            // Fetch all gist files if not cached
            if (!this.gistFilesCache) {
                const response = await fetch(
                    `https://api.github.com/gists/${this.config.gistId}`,
                    {
                        headers: {
                            Authorization: `token ${this.config.gistToken}`,
                            Accept: 'application/vnd.github.v3+json',
                        },
                    }
                );

                if (!response.ok) return null;

                const gist = await response.json();
                this.gistFilesCache = new Map();

                for (const [filename, fileData] of Object.entries(gist.files)) {
                    try {
                        const content = (fileData as { content: string }).content;
                        this.gistFilesCache.set(filename, JSON.parse(content));
                    } catch {
                        // Skip non-JSON files
                    }
                }
            }

            // Look for cache entry
            const cacheFileName = `cache_${key}.json`;
            const cached = this.gistFilesCache.get(cacheFileName);
            if (cached) {
                return cached as CacheEntry<T>;
            }

            // Also check for raw data files (legacy format)
            const rawFileName = `${key}.json`;
            const rawData = this.gistFilesCache.get(rawFileName);
            if (rawData) {
                // Wrap in cache entry format
                return {
                    data: rawData as T,
                    timestamp: Date.now(),
                    checksum: simpleHash(JSON.stringify(rawData)),
                    ttl: this.config.defaultTTL,
                };
            }

            return null;
        } catch (e) {
            console.warn(`[Cache L3] Gist fetch failed:`, e);
            return null;
        }
    }

    private async saveToGist<T>(key: string, entry: CacheEntry<T>): Promise<void> {
        if (!this.config.gistId || !this.config.gistToken) {
            console.warn('[Cache L3] No Gist credentials, skipping');
            return;
        }

        try {
            const filename = `cache_${key}.json`;

            await fetch(`https://api.github.com/gists/${this.config.gistId}`, {
                method: 'PATCH',
                headers: {
                    Authorization: `token ${this.config.gistToken}`,
                    Accept: 'application/vnd.github.v3+json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    files: {
                        [filename]: {
                            content: JSON.stringify(entry, null, 2),
                        },
                    },
                }),
            });

            // Invalidate cache
            this.gistFilesCache = null;
        } catch (e) {
            console.warn(`[Cache L3] Gist save failed:`, e);
        }
    }

    /**
     * Clear all cache tiers for a specific key
     */
    async clear(key: string): Promise<void> {
        this.memory.delete(key);
        localStorage.removeItem(`olapxtrctr_${key}`);
        // Note: Gist files are not deleted, just ignored
        console.log(`[Cache] CLEARED: ${key}`);
    }

    /**
     * Clear entire cache
     */
    async clearAll(): Promise<void> {
        this.memory.clear();

        // Clear localStorage entries with our prefix
        const keysToRemove: string[] = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key?.startsWith('olapxtrctr_')) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(k => localStorage.removeItem(k));

        this.gistFilesCache = null;
        console.log(`[Cache] CLEARED ALL`);
    }

    /**
     * Invalidate Gist cache to force refresh
     */
    invalidateGistCache(): void {
        this.gistFilesCache = null;
    }

    /**
     * Get cache health status
     */
    async getStatus(): Promise<{
        memory: number;
        localStorage: number;
        gistConnected: boolean;
    }> {
        let localStorageCount = 0;
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key?.startsWith('olapxtrctr_')) {
                localStorageCount++;
            }
        }

        let gistConnected = false;
        if (this.config.gistId && this.config.gistToken) {
            try {
                const response = await fetch(
                    `https://api.github.com/gists/${this.config.gistId}`,
                    {
                        method: 'HEAD',
                        headers: {
                            Authorization: `token ${this.config.gistToken}`,
                        },
                    }
                );
                gistConnected = response.ok;
            } catch {
                gistConnected = false;
            }
        }

        return {
            memory: this.memory.size,
            localStorage: localStorageCount,
            gistConnected,
        };
    }

    /**
     * Validate specific cached entry
     */
    async validate(key: string): Promise<{
        exists: boolean;
        valid: boolean;
        tier: 'memory' | 'localStorage' | 'gist' | null;
        age?: number;
    }> {
        // Check L1
        const memEntry = this.memory.get(key);
        if (memEntry) {
            return {
                exists: true,
                valid: this.isValid(memEntry as CacheEntry<unknown>),
                tier: 'memory',
                age: Date.now() - memEntry.timestamp,
            };
        }

        // Check L2
        const localEntry = this.getFromLocalStorage(key);
        if (localEntry) {
            return {
                exists: true,
                valid: this.isValid(localEntry),
                tier: 'localStorage',
                age: Date.now() - localEntry.timestamp,
            };
        }

        // Check L3
        const gistEntry = await this.getFromGist(key);
        if (gistEntry) {
            return {
                exists: true,
                valid: this.isValid(gistEntry),
                tier: 'gist',
                age: Date.now() - gistEntry.timestamp,
            };
        }

        return { exists: false, valid: false, tier: null };
    }

    /**
     * Get with fallback function (for cache miss recovery)
     */
    async getOrFetch<T>(
        key: string,
        fetchFn: () => Promise<T>,
        ttl?: number
    ): Promise<T> {
        // Try cache first
        const cached = await this.get<T>(key);
        if (cached !== null) {
            return cached;
        }

        // Cache miss - fetch and save
        console.log(`[Cache] Fetching fresh data for: ${key}`);
        const data = await fetchFn();
        await this.set(key, data, ttl);
        return data;
    }
}

// Singleton instance
export const smartCache = new SmartCache();

// Export class for testing
export { SmartCache };
export type { CacheEntry, CacheConfig };
