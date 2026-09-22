import type { FileCategory } from "../../types";

const FILE_CATEGORY_ACCEPT: Record<FileCategory, string> = {
  image:
    "image/*,.heic,.heif,.avif,.webp,.bmp,.ico,.tiff,.tif,.svg,.psd,.eps,.tga,.pcx,.jxl,.dng",
  video:
    "video/*,.mkv,.flv,.wmv,.avi,.mov,.m4v,.mpeg,.mpg,.3gp,.3g2,.ogv,.ts,.mts,.m2ts,.vob,.divx,.rm,.rmvb,.f4v",
  audio:
    "audio/*,.m4a,.mp3,.wav,.ogg,.aac,.flac,.wma,.opus,.aiff,.caf,.amr,.mid,.midi,.ape,.alac,.wv",
  document:
    ".pdf,.doc,.docx,.dot,.dotx,.docm,.xls,.xlsx,.xlsm,.csv,.xlt,.ods,.ppt,.pptx,.potx,.ppsx,.pptm,.odp,.vsd,.vsdx,.vsdm,.txt,.md,.csv,.rtf,.odt,.epub,.dxf,.dwg,.log,.json,.xml,.html,.htm,.yaml,.yml,.toml,.ini,.cfg,.tex,.diff,.patch,.py,.js,.ts,.jsx,.tsx,.vue,.svelte,.go,.rs,.rb,.php,.java,.c,.cpp,.h,.cs,.swift,.kt,.scala,.dart,.lua,.r,.pl,.sql,.sh,.bash,.zsh,.fish,.ps1,.bat,.cmd,.properties,.gradle,.cmake,.env,.graphql,.proto,.zip,.rar,.7z,.tar,.gz,.bz2,.xz,.tgz",
};

const ALL_FILE_CATEGORIES = Object.keys(FILE_CATEGORY_ACCEPT) as FileCategory[];

// accept 里出现 image/* 会让 Android 13+ 直接弹系统照片选择器（部分 WebView
// 连「浏览文件」入口都没有），四类全放行时必须留空让系统弹完整选择器。
export function getFileAccept(categories: FileCategory[]): string {
  if (ALL_FILE_CATEGORIES.every((category) => categories.includes(category))) {
    return "";
  }
  return categories.map((category) => FILE_CATEGORY_ACCEPT[category]).join(",");
}
