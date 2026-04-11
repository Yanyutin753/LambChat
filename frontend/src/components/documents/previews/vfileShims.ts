const VFILE_INDEX_SHIM = `import {VFileMessage} from 'vfile-message'
import {minpath} from './minpath.browser.js'
import {minproc} from './minproc.browser.js'
import {urlToPath, isUrl} from './minurl.browser.js'

const order = ['history', 'path', 'basename', 'stem', 'extname', 'dirname']

export class VFile {
  constructor(value) {
    let options
    if (!value) { options = {} }
    else if (isUrl(value)) { options = { path: value } }
    else if (typeof value === 'string' || isUint8Array(value)) { options = { value } }
    else { options = value }
    this.cwd = 'cwd' in options ? '' : minproc.cwd()
    this.data = {}
    this.history = []
    this.messages = []
    this.value = undefined
    this.map = undefined
    this.result = undefined
    this.stored = undefined
    let index = -1
    while (++index < order.length) {
      const field = order[index]
      if (field in options && options[field] !== undefined && options[field] !== null) {
        this[field] = field === 'history' ? [...options[field]] : options[field]
      }
    }
    let field
    for (field in options) {
      if (!order.includes(field)) this[field] = options[field]
    }
  }
  get basename() { return typeof this.path === 'string' ? minpath.basename(this.path) : undefined }
  set basename(v) {
    assertNonEmpty(v, 'basename')
    assertPart(v, 'basename')
    this.path = minpath.join(this.dirname || '', v)
  }
  get dirname() { return typeof this.path === 'string' ? minpath.dirname(this.path) : undefined }
  set dirname(v) {
    assertPath(this.basename, 'dirname')
    this.path = minpath.join(v || '', this.basename)
  }
  get extname() { return typeof this.path === 'string' ? minpath.extname(this.path) : undefined }
  set extname(v) {
    assertPart(v, 'extname')
    assertPath(this.dirname, 'extname')
    if (v) {
      if (v.codePointAt(0) !== 46) throw new Error('\`extname\` must start with \`.\`')
      if (v.includes('.', 1)) throw new Error('\`extname\` cannot contain multiple dots')
    }
    this.path = minpath.join(this.dirname, this.stem + (v || ''))
  }
  get path() { return this.history[this.history.length - 1] }
  set path(v) {
    if (isUrl(v)) v = urlToPath(v)
    assertNonEmpty(v, 'path')
    if (this.path !== v) this.history.push(v)
  }
  get stem() { return typeof this.path === 'string' ? minpath.basename(this.path, this.extname) : undefined }
  set stem(v) {
    assertNonEmpty(v, 'stem')
    assertPart(v, 'stem')
    this.path = minpath.join(this.dirname || '', v + (this.extname || ''))
  }
  fail(causeOrReason, optionsOrParentOrPlace, origin) {
    const message = this.message(causeOrReason, optionsOrParentOrPlace, origin)
    message.fatal = true
    throw message
  }
  info(causeOrReason, optionsOrParentOrPlace, origin) {
    const message = this.message(causeOrReason, optionsOrParentOrPlace, origin)
    message.fatal = undefined
    return message
  }
  message(causeOrReason, optionsOrParentOrPlace, origin) {
    const message = new VFileMessage(causeOrReason, optionsOrParentOrPlace, origin)
    if (this.path) { message.name = this.path + ':' + message.name; message.file = this.path }
    message.fatal = false
    this.messages.push(message)
    return message
  }
  toString(encoding) {
    if (this.value === undefined) return ''
    if (typeof this.value === 'string') return this.value
    return new TextDecoder(encoding || undefined).decode(this.value)
  }
}

function assertPart(part, name) {
  if (part && part.includes(minpath.sep)) {
    throw new Error('\`' + name + '\` cannot be a path: did not expect \`/\`')
  }
}

function assertNonEmpty(part, name) {
  if (!part) throw new Error('\`' + name + '\` cannot be empty')
}

function assertPath(path, name) {
  if (!path) throw new Error('Setting \`' + name + '\` requires \`path\` to be set too')
}

function isUint8Array(value) {
  return Boolean(value && typeof value === 'object' && 'byteLength' in value && 'byteOffset' in value)
}
`;

const MINPATH_BROWSER_SHIM = `function assertPath(path) {
  if (typeof path !== 'string') throw new TypeError('Path must be a string')
}

function basename(path, extname) {
  assertPath(path)
  if (extname !== undefined && typeof extname !== 'string') {
    throw new TypeError('"ext" argument must be a string')
  }
  let index = path.length
  if (extname === undefined || extname.length === 0 || extname.length > path.length) {
    while (index--) {
      if (path.codePointAt(index) === 47) {
        if (path.codePointAt(index + 1) !== 46 || path.codePointAt(index + 2) === 47) {
          return path.slice(index + 1)
        }
      }
    }
    return path || ''
  }
  let start = -1
  let extnameIndex = extname.length - 1
  while (index--) {
    if (path.codePointAt(index) === 47) {
      if (start < 0) start = index + 1
    } else {
      if (extnameIndex >= 0) {
        if (path.codePointAt(index) === extname.codePointAt(extnameIndex--)) {
          if (extnameIndex < 0) start = index
        } else {
          extnameIndex = -1
        }
      } else {
        start = index + 1
      }
    }
  }
  return start < 0 ? path : path.slice(start)
}

function dirname(path) {
  assertPath(path)
  if (path.length === 0) return '.'
  let index = path.length
  while (--index && path.codePointAt(index) !== 47);
  return index <= 0 ? '.' : path.slice(0, index)
}

function extname(path) {
  assertPath(path)
  let index = path.length
  let end = -1
  let seenNonDot = 0
  while (index--) {
    if (path.codePointAt(index) === 47) {
      if (end >= 0 && seenNonDot === 1 && path.codePointAt(index + 1) === 46) {
        return path.slice(index + 1, end + 1)
      }
      end = -1
      seenNonDot = 0
    } else if (path.codePointAt(index) === 46) {
      if (end < 0) end = index + 1
    } else if (end >= 0) {
      seenNonDot = 1
    }
  }
  return ''
}

function join(...segments) {
  let result
  for (let index = 0; index < segments.length; index++) {
    assertPath(segments[index])
    result =
      result === undefined
        ? segments[index]
        : result + (result.endsWith('/') ? '' : '/') + segments[index]
  }
  return result === undefined ? '.' : result
}

export const minpath = { basename, dirname, extname, join, sep: '/' }
`;

const MINPROC_BROWSER_SHIM = `export const minproc = {cwd: () => '/' }
`;

const MINURL_SHARED_SHIM = `export function isUrl(fileUrlOrPath) {
  return Boolean(
    fileUrlOrPath !== null &&
      typeof fileUrlOrPath === 'object' &&
      'href' in fileUrlOrPath &&
      fileUrlOrPath.href &&
      'protocol' in fileUrlOrPath &&
      fileUrlOrPath.protocol &&
      fileUrlOrPath.auth === undefined
  )
}
`;

const MINURL_BROWSER_SHIM = `import {isUrl} from './minurl.shared.js'

export {isUrl} from './minurl.shared.js'

export function urlToPath(path) {
  if (typeof path === 'string') {
    path = new URL(path)
  } else if (!isUrl(path)) {
    const error = new TypeError(
      'The "path" argument must be of type string or an instance of URL'
    )
    error.code = 'ERR_INVALID_ARG_TYPE'
    throw error
  }

  if (path.protocol !== 'file:') {
    const error = new TypeError('The URL must be of scheme file')
    error.code = 'ERR_INVALID_URL_SCHEME'
    throw error
  }

  return decodeURIComponent(path.pathname)
}
`;

export const VFILE_SHIMS: Record<string, string> = {
  "/node_modules/vfile/lib/index.js": VFILE_INDEX_SHIM,
  "/node_modules/vfile/lib/minpath.browser.js": MINPATH_BROWSER_SHIM,
  "/node_modules/vfile/lib/minproc.browser.js": MINPROC_BROWSER_SHIM,
  "/node_modules/vfile/lib/minurl.browser.js": MINURL_BROWSER_SHIM,
  "/node_modules/vfile/lib/minurl.shared.js": MINURL_SHARED_SHIM,
};
