import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
/**
 * A sandboxed fs wrapper that restricts all file operations to allowed directories.
 * Any attempt to access files outside the allowed directories will throw an EPERM error.
 *
 * By default, allows access to:
 * - Current working directory (process.cwd())
 * - /tmp
 * - os.tmpdir()
 *
 * This is used in the MCP VM context to prevent agents from accessing sensitive system files.
 */
export class ScopedFS {
    allowedDirs;
    constructor(allowedDirs) {
        // Default allowed directories: cwd, /tmp, os.tmpdir()
        const defaultDirs = [process.cwd(), '/tmp', os.tmpdir()];
        // Use provided dirs or defaults, resolve all to absolute paths
        const dirs = allowedDirs ?? defaultDirs;
        this.allowedDirs = [...new Set(dirs.map((d) => path.resolve(d)))];
    }
    /**
     * Check if a resolved path is within any of the allowed directories.
     */
    isPathAllowed(resolved) {
        return this.allowedDirs.some((dir) => {
            return resolved === dir || resolved.startsWith(dir + path.sep);
        });
    }
    /**
     * Resolve a path and ensure it stays within allowed directories.
     * Throws EPERM if the resolved path escapes the sandbox.
     */
    resolvePath(filePath) {
        // If it's an absolute path, use it directly
        // If it's relative, resolve from cwd
        const resolved = path.resolve(filePath);
        if (!this.isPathAllowed(resolved)) {
            const error = new Error(`EPERM: operation not permitted, access outside allowed directories: ${filePath}`);
            error.code = 'EPERM';
            error.errno = -1;
            error.syscall = 'access';
            error.path = filePath;
            throw error;
        }
        return resolved;
    }
    // Sync methods
    readFileSync = (filePath, options) => {
        const resolved = this.resolvePath(filePath.toString());
        return fs.readFileSync(resolved, options);
    };
    writeFileSync = (filePath, data, options) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.writeFileSync(resolved, data, options);
    };
    appendFileSync = (filePath, data, options) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.appendFileSync(resolved, data, options);
    };
    readdirSync = (dirPath, options) => {
        const resolved = this.resolvePath(dirPath.toString());
        return fs.readdirSync(resolved, options);
    };
    mkdirSync = (dirPath, options) => {
        const resolved = this.resolvePath(dirPath.toString());
        return fs.mkdirSync(resolved, options);
    };
    rmdirSync = (dirPath, options) => {
        const resolved = this.resolvePath(dirPath.toString());
        fs.rmdirSync(resolved, options);
    };
    unlinkSync = (filePath) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.unlinkSync(resolved);
    };
    statSync = (filePath, options) => {
        const resolved = this.resolvePath(filePath.toString());
        return fs.statSync(resolved, options);
    };
    lstatSync = (filePath, options) => {
        const resolved = this.resolvePath(filePath.toString());
        return fs.lstatSync(resolved, options);
    };
    existsSync = (filePath) => {
        try {
            const resolved = this.resolvePath(filePath.toString());
            return fs.existsSync(resolved);
        }
        catch {
            return false;
        }
    };
    accessSync = (filePath, mode) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.accessSync(resolved, mode);
    };
    copyFileSync = (src, dest, mode) => {
        const resolvedSrc = this.resolvePath(src.toString());
        const resolvedDest = this.resolvePath(dest.toString());
        fs.copyFileSync(resolvedSrc, resolvedDest, mode);
    };
    renameSync = (oldPath, newPath) => {
        const resolvedOld = this.resolvePath(oldPath.toString());
        const resolvedNew = this.resolvePath(newPath.toString());
        fs.renameSync(resolvedOld, resolvedNew);
    };
    chmodSync = (filePath, mode) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.chmodSync(resolved, mode);
    };
    chownSync = (filePath, uid, gid) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.chownSync(resolved, uid, gid);
    };
    utimesSync = (filePath, atime, mtime) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.utimesSync(resolved, atime, mtime);
    };
    realpathSync = (filePath, options) => {
        const resolved = this.resolvePath(filePath.toString());
        const real = fs.realpathSync(resolved, options);
        // Verify the real path is also within allowed directories (handles symlinks)
        const realStr = real.toString();
        if (!this.isPathAllowed(realStr)) {
            const error = new Error(`EPERM: operation not permitted, realpath escapes allowed directories`);
            error.code = 'EPERM';
            throw error;
        }
        return real;
    };
    readlinkSync = (filePath, options) => {
        const resolved = this.resolvePath(filePath.toString());
        return fs.readlinkSync(resolved, options);
    };
    symlinkSync = (target, linkPath, type) => {
        const resolvedLink = this.resolvePath(linkPath.toString());
        // Target is relative to link location, resolve it to check bounds
        const linkDir = path.dirname(resolvedLink);
        const resolvedTarget = path.resolve(linkDir, target.toString());
        if (!this.isPathAllowed(resolvedTarget)) {
            const error = new Error(`EPERM: operation not permitted, symlink target outside allowed directories`);
            error.code = 'EPERM';
            throw error;
        }
        fs.symlinkSync(target, resolvedLink, type);
    };
    rmSync = (filePath, options) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.rmSync(resolved, options);
    };
    // Async callback methods
    readFile = (filePath, ...args) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.readFile(resolved, ...args);
    };
    writeFile = (filePath, data, ...args) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.writeFile(resolved, data, ...args);
    };
    appendFile = (filePath, data, ...args) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.appendFile(resolved, data, ...args);
    };
    readdir = (dirPath, ...args) => {
        const resolved = this.resolvePath(dirPath.toString());
        fs.readdir(resolved, ...args);
    };
    mkdir = (dirPath, ...args) => {
        const resolved = this.resolvePath(dirPath.toString());
        fs.mkdir(resolved, ...args);
    };
    rmdir = (dirPath, ...args) => {
        const resolved = this.resolvePath(dirPath.toString());
        fs.rmdir(resolved, ...args);
    };
    unlink = (filePath, callback) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.unlink(resolved, callback);
    };
    stat = (filePath, ...args) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.stat(resolved, ...args);
    };
    lstat = (filePath, ...args) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.lstat(resolved, ...args);
    };
    access = (filePath, ...args) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.access(resolved, ...args);
    };
    copyFile = (src, dest, ...args) => {
        const resolvedSrc = this.resolvePath(src.toString());
        const resolvedDest = this.resolvePath(dest.toString());
        fs.copyFile(resolvedSrc, resolvedDest, ...args);
    };
    rename = (oldPath, newPath, callback) => {
        const resolvedOld = this.resolvePath(oldPath.toString());
        const resolvedNew = this.resolvePath(newPath.toString());
        fs.rename(resolvedOld, resolvedNew, callback);
    };
    chmod = (filePath, mode, callback) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.chmod(resolved, mode, callback);
    };
    chown = (filePath, uid, gid, callback) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.chown(resolved, uid, gid, callback);
    };
    rm = (filePath, ...args) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.rm(resolved, ...args);
    };
    exists = (filePath, callback) => {
        try {
            const resolved = this.resolvePath(filePath.toString());
            fs.exists(resolved, callback);
        }
        catch {
            callback(false);
        }
    };
    // Stream methods
    createReadStream = (filePath, options) => {
        const resolved = this.resolvePath(filePath.toString());
        return fs.createReadStream(resolved, options);
    };
    createWriteStream = (filePath, options) => {
        const resolved = this.resolvePath(filePath.toString());
        return fs.createWriteStream(resolved, options);
    };
    // Watch methods
    watch = (filePath, ...args) => {
        const resolved = this.resolvePath(filePath.toString());
        return fs.watch(resolved, ...args);
    };
    watchFile = (filePath, ...args) => {
        const resolved = this.resolvePath(filePath.toString());
        return fs.watchFile(resolved, ...args);
    };
    unwatchFile = (filePath, listener) => {
        const resolved = this.resolvePath(filePath.toString());
        fs.unwatchFile(resolved, listener);
    };
    // Promise-based API (fs.promises equivalent)
    get promises() {
        const self = this;
        return {
            readFile: async (filePath, options) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.readFile(resolved, options);
            },
            writeFile: async (filePath, data, options) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.writeFile(resolved, data, options);
            },
            appendFile: async (filePath, data, options) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.appendFile(resolved, data, options);
            },
            readdir: async (dirPath, options) => {
                const resolved = self.resolvePath(dirPath.toString());
                return fs.promises.readdir(resolved, options);
            },
            mkdir: async (dirPath, options) => {
                const resolved = self.resolvePath(dirPath.toString());
                return fs.promises.mkdir(resolved, options);
            },
            rmdir: async (dirPath, options) => {
                const resolved = self.resolvePath(dirPath.toString());
                return fs.promises.rmdir(resolved, options);
            },
            unlink: async (filePath) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.unlink(resolved);
            },
            stat: async (filePath, options) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.stat(resolved, options);
            },
            lstat: async (filePath, options) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.lstat(resolved, options);
            },
            access: async (filePath, mode) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.access(resolved, mode);
            },
            copyFile: async (src, dest, mode) => {
                const resolved = self.resolvePath(src.toString());
                const resolvedDest = self.resolvePath(dest.toString());
                return fs.promises.copyFile(resolved, resolvedDest, mode);
            },
            rename: async (oldPath, newPath) => {
                const resolvedOld = self.resolvePath(oldPath.toString());
                const resolvedNew = self.resolvePath(newPath.toString());
                return fs.promises.rename(resolvedOld, resolvedNew);
            },
            chmod: async (filePath, mode) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.chmod(resolved, mode);
            },
            chown: async (filePath, uid, gid) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.chown(resolved, uid, gid);
            },
            rm: async (filePath, options) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.rm(resolved, options);
            },
            realpath: async (filePath, options) => {
                const resolved = self.resolvePath(filePath.toString());
                const real = await fs.promises.realpath(resolved, options);
                const realStr = real.toString();
                if (!self.isPathAllowed(realStr)) {
                    const error = new Error(`EPERM: operation not permitted, realpath escapes allowed directories`);
                    error.code = 'EPERM';
                    throw error;
                }
                return real;
            },
            readlink: async (filePath, options) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.readlink(resolved, options);
            },
            symlink: async (target, linkPath, type) => {
                const resolvedLink = self.resolvePath(linkPath.toString());
                const linkDir = path.dirname(resolvedLink);
                const resolvedTarget = path.resolve(linkDir, target.toString());
                if (!self.isPathAllowed(resolvedTarget)) {
                    const error = new Error(`EPERM: operation not permitted, symlink target outside allowed directories`);
                    error.code = 'EPERM';
                    throw error;
                }
                return fs.promises.symlink(target, resolvedLink, type);
            },
            utimes: async (filePath, atime, mtime) => {
                const resolved = self.resolvePath(filePath.toString());
                return fs.promises.utimes(resolved, atime, mtime);
            },
        };
    }
    // Constants passthrough
    constants = fs.constants;
}
/**
 * Create a scoped fs instance with allowed directories.
 * Defaults to cwd, /tmp, and os.tmpdir() if no directories specified.
 */
export function createScopedFS(allowedDirs) {
    return new ScopedFS(allowedDirs);
}
//# sourceMappingURL=scoped-fs.js.map