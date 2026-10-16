import {
  Children,
  isValidElement,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import type { LucideProps } from "lucide-react";
import type { IconHandle } from "@animateicons/react";
import { PanelLeftIcon as AnimatedPanelLeft } from "@animateicons/react/lucide/panel-left-icon";
import { PlusIcon as AnimatedPlus } from "@animateicons/react/lucide/plus-icon";
import { MinusIcon as AnimatedMinus } from "@animateicons/react/lucide/minus-icon";
import { CheckIcon as AnimatedCheck } from "@animateicons/react/lucide/check-icon";
import { XIcon as AnimatedX } from "@animateicons/react/lucide/x-icon";
import { CopyIcon as AnimatedCopy } from "@animateicons/react/lucide/copy-icon";
import { DownloadIcon as AnimatedDownload } from "@animateicons/react/lucide/download-icon";
import { UploadIcon as AnimatedUpload } from "@animateicons/react/lucide/upload-icon";
import { ExternalLinkIcon as AnimatedExternalLink } from "@animateicons/react/lucide/external-link-icon";
import { SearchIcon as AnimatedSearch } from "@animateicons/react/lucide/search-icon";
import { BellIcon as AnimatedBell } from "@animateicons/react/lucide/bell-icon";
import { StarIcon as AnimatedStar } from "@animateicons/react/lucide/star-icon";
import { Trash2Icon as AnimatedTrash2 } from "@animateicons/react/lucide/trash-2-icon";
import { PencilIcon as AnimatedPencil } from "@animateicons/react/lucide/pencil-icon";
import { EllipsisIcon as AnimatedMoreHorizontal } from "@animateicons/react/lucide/ellipsis-icon";
import { ChevronDownIcon as AnimatedChevronDown } from "@animateicons/react/lucide/chevron-down-icon";
import { ChevronUpIcon as AnimatedChevronUp } from "@animateicons/react/lucide/chevron-up-icon";
import { ChevronLeftIcon as AnimatedChevronLeft } from "@animateicons/react/lucide/chevron-left-icon";
import { ChevronRightIcon as AnimatedChevronRight } from "@animateicons/react/lucide/chevron-right-icon";
import { ArrowUpIcon as AnimatedArrowUp } from "@animateicons/react/lucide/arrow-up-icon";
import { ArrowDownIcon as AnimatedArrowDown } from "@animateicons/react/lucide/arrow-down-icon";
import { ArrowLeftIcon as AnimatedArrowLeft } from "@animateicons/react/lucide/arrow-left-icon";
import { ArrowRightIcon as AnimatedArrowRight } from "@animateicons/react/lucide/arrow-right-icon";
import { CalendarClockIcon as AnimatedCalendarClock } from "@animateicons/react/lucide/calendar-clock-icon";
import { FolderOpenIcon as AnimatedFolderOpen } from "@animateicons/react/lucide/folder-open-icon";
import { FolderIcon as AnimatedFolder } from "@animateicons/react/lucide/folder-icon";
import { FolderPlusIcon as AnimatedFolderPlus } from "@animateicons/react/lucide/folder-plus-icon";
import { MessageCircleIcon as AnimatedMessageCircle } from "@animateicons/react/lucide/message-circle-icon";
import { NetworkIcon as AnimatedNetwork } from "@animateicons/react/lucide/network-icon";
import { BrainIcon as AnimatedBrain } from "@animateicons/react/lucide/brain-icon";
import { UsersIcon as AnimatedUsers } from "@animateicons/react/lucide/users-icon";
import { UserRoundIcon as AnimatedUserRound } from "@animateicons/react/lucide/user-round-icon";
import { SparklesIcon as AnimatedSparkles } from "@animateicons/react/lucide/sparkles-icon";
import { ServerIcon as AnimatedServer } from "@animateicons/react/lucide/server-icon";
import { CloudIcon as AnimatedCloud } from "@animateicons/react/lucide/cloud-icon";
import { MonitorIcon as AnimatedMonitor } from "@animateicons/react/lucide/monitor-icon";
import { SettingsIcon as AnimatedSettings } from "@animateicons/react/lucide/settings-icon";
import { PaperclipIcon as AnimatedPaperclip } from "@animateicons/react/lucide/paperclip-icon";
import { FileTextIcon as AnimatedFileText } from "@animateicons/react/lucide/file-text-icon";
import { ImageIcon as AnimatedImage } from "@animateicons/react/lucide/image-icon";
import { VideoIcon as AnimatedVideo } from "@animateicons/react/lucide/video-icon";
import { MusicIcon as AnimatedMusic } from "@animateicons/react/lucide/music-icon";
import { KeyboardIcon as AnimatedKeyboard } from "@animateicons/react/lucide/keyboard-icon";
import { ZapIcon as AnimatedZap } from "@animateicons/react/lucide/zap-icon";
import { TargetIcon as AnimatedTarget } from "@animateicons/react/lucide/target-icon";
import { PinIcon as AnimatedPin } from "@animateicons/react/lucide/pin-icon";
import { LockIcon as AnimatedLock } from "@animateicons/react/lucide/lock-icon";
import { RefreshCwIcon as AnimatedRefreshCw } from "@animateicons/react/lucide/refresh-cw-icon";
import { RotateCcwIcon as AnimatedRotateCcw } from "@animateicons/react/lucide/rotate-ccw-icon";
import { SquarePenIcon as AnimatedSquarePen } from "@animateicons/react/lucide/square-pen-icon";
import { HeartIcon as AnimatedHeart } from "@animateicons/react/lucide/heart-icon";
import { BookmarkIcon as AnimatedBookmark } from "@animateicons/react/lucide/bookmark-icon";
import { EyeIcon as AnimatedEye } from "@animateicons/react/lucide/eye-icon";
import { FilterIcon as AnimatedFilter } from "@animateicons/react/lucide/filter-icon";
import { SlidersHorizontalIcon as AnimatedSlidersHorizontal } from "@animateicons/react/lucide/sliders-horizontal-icon";
import { LogOutIcon as AnimatedLogOut } from "@animateicons/react/lucide/log-out-icon";
import { MenuIcon as AnimatedMenu } from "@animateicons/react/lucide/menu-icon";
import { InfoIcon as AnimatedInfo } from "@animateicons/react/lucide/info-icon";
import { CircleXIcon as AnimatedCircleX } from "@animateicons/react/lucide/circle-x-icon";
import { ShareIcon as AnimatedShare } from "@animateicons/react/lucide/share-icon";
import { CircleQuestionMarkIcon as AnimatedHelp } from "@animateicons/react/lucide/circle-question-mark-icon";
import { ActivityIcon as AnimatedActivity } from "@animateicons/react/lucide/activity-icon";
import { CircleAlertIcon as AnimatedAlertCircle } from "@animateicons/react/lucide/circle-alert-icon";
import { ArchiveIcon as AnimatedArchive } from "@animateicons/react/lucide/archive-icon";
import { ArrowUpDownIcon as AnimatedArrowUpDown } from "@animateicons/react/lucide/arrow-up-down-icon";
import { BotIcon as AnimatedBot } from "@animateicons/react/lucide/bot-icon";
import { ChevronsUpDownIcon as AnimatedChevronsUpDown } from "@animateicons/react/lucide/chevrons-up-down-icon";
import { ClockIcon as AnimatedClock } from "@animateicons/react/lucide/clock-icon";
import { CodeIcon as AnimatedCode } from "@animateicons/react/lucide/code-icon";
import { CodeIcon as AnimatedCode2 } from "@animateicons/react/lucide/code-icon";
import { CoffeeIcon as AnimatedCoffee } from "@animateicons/react/lucide/coffee-icon";
import { CornerDownRightIcon as AnimatedCornerDownRight } from "@animateicons/react/lucide/corner-down-right-icon";
import { CornerRightUpIcon as AnimatedCornerRightUp } from "@animateicons/react/lucide/corner-right-up-icon";
import { CpuIcon as AnimatedCpu } from "@animateicons/react/lucide/cpu-icon";
import { ExpandIcon as AnimatedExpand } from "@animateicons/react/lucide/expand-icon";
import { EyeOffIcon as AnimatedEyeOff } from "@animateicons/react/lucide/eye-off-icon";
import { FileIcon as AnimatedFile } from "@animateicons/react/lucide/file-icon";
import { FileArchiveIcon as AnimatedFileArchive } from "@animateicons/react/lucide/file-archive-icon";
import { FolderClosedIcon as AnimatedFolderClosed } from "@animateicons/react/lucide/folder-closed-icon";
import { FolderHeartIcon as AnimatedFolderHeart } from "@animateicons/react/lucide/folder-heart-icon";
import { FolderTreeIcon as AnimatedFolderTree } from "@animateicons/react/lucide/folder-tree-icon";
import { GitBranchIcon as AnimatedGitBranch } from "@animateicons/react/lucide/git-branch-icon";
import { GlobeIcon as AnimatedGlobe } from "@animateicons/react/lucide/globe-icon";
import { HashIcon as AnimatedHash } from "@animateicons/react/lucide/hash-icon";
import { HistoryIcon as AnimatedHistory } from "@animateicons/react/lucide/history-icon";
import { ImageIcon as AnimatedImageIcon } from "@animateicons/react/lucide/image-icon";
import { LayoutGridIcon as AnimatedLayoutGrid } from "@animateicons/react/lucide/layout-grid-icon";
import { LightbulbIcon as AnimatedLightbulb } from "@animateicons/react/lucide/lightbulb-icon";
import { ListIcon as AnimatedList } from "@animateicons/react/lucide/list-icon";
import { ListChecksIcon as AnimatedListChecks } from "@animateicons/react/lucide/list-checks-icon";
import { MoonIcon as AnimatedMoon } from "@animateicons/react/lucide/moon-icon";
import { PauseIcon as AnimatedPause } from "@animateicons/react/lucide/pause-icon";
import { PlayIcon as AnimatedPlay } from "@animateicons/react/lucide/play-icon";
import { SaveIcon as AnimatedSave } from "@animateicons/react/lucide/save-icon";
import { SendIcon as AnimatedSend } from "@animateicons/react/lucide/send-icon";
import { ShieldCheckIcon as AnimatedShieldCheck } from "@animateicons/react/lucide/shield-check-icon";
import { ShrinkIcon as AnimatedShrink } from "@animateicons/react/lucide/shrink-icon";
import { SunIcon as AnimatedSun } from "@animateicons/react/lucide/sun-icon";
import { TagIcon as AnimatedTag } from "@animateicons/react/lucide/tag-icon";
import { ThumbsDownIcon as AnimatedThumbsDown } from "@animateicons/react/lucide/thumbs-down-icon";
import { ThumbsUpIcon as AnimatedThumbsUp } from "@animateicons/react/lucide/thumbs-up-icon";
import { TimerIcon as AnimatedTimer } from "@animateicons/react/lucide/timer-icon";
import { ToggleLeftIcon as AnimatedToggleLeft } from "@animateicons/react/lucide/toggle-left-icon";
import { ToggleRightIcon as AnimatedToggleRight } from "@animateicons/react/lucide/toggle-right-icon";
import { TypeIcon as AnimatedType } from "@animateicons/react/lucide/type-icon";
import { CloudUploadIcon as AnimatedUploadCloud } from "@animateicons/react/lucide/cloud-upload-icon";
import { WrenchIcon as AnimatedWrench } from "@animateicons/react/lucide/wrench-icon";

import { AtSignIcon as AnimatedAtSign } from "@animateicons/react/lucide/at-sign-icon";
import { UserIcon as AnimatedUser } from "@animateicons/react/lucide/user-icon";
import { MailIcon as AnimatedMail } from "@animateicons/react/lucide/mail-icon";
import { BanIcon as AnimatedBan } from "@animateicons/react/lucide/ban-icon";
import { ImagePlusIcon as AnimatedImagePlus } from "@animateicons/react/lucide/image-plus-icon";
import { BookOpenIcon as AnimatedBookOpen } from "@animateicons/react/lucide/book-open-icon";
import { BoxIcon as AnimatedBox } from "@animateicons/react/lucide/box-icon";
import { WifiOffIcon as AnimatedWifiOff } from "@animateicons/react/lucide/wifi-off-icon";
import { CircleCheckIcon as AnimatedCircleCheck } from "@animateicons/react/lucide/circle-check-icon";
import { MicIcon as AnimatedMic } from "@animateicons/react/lucide/mic-icon";
import { LanguagesIcon as AnimatedLanguages } from "@animateicons/react/lucide/languages-icon";
import { MousePointerClickIcon as AnimatedMousePointerClick } from "@animateicons/react/lucide/mouse-pointer-click-icon";
import { MessageSquareTextIcon as AnimatedMessageSquareText } from "@animateicons/react/lucide/message-square-text-icon";
import { FileScanIcon as AnimatedFileScan } from "@animateicons/react/lucide/file-scan-icon";
import { LayersIcon as AnimatedLayers } from "@animateicons/react/lucide/layers-icon";
import { KeyRoundIcon as AnimatedKeyRound } from "@animateicons/react/lucide/key-round-icon";
import { TriangleAlertIcon as AnimatedTriangleAlert } from "@animateicons/react/lucide/triangle-alert-icon";
import { TerminalIcon as AnimatedTerminal } from "@animateicons/react/lucide/terminal-icon";
import { FolderSearchIcon as AnimatedFolderSearch } from "@animateicons/react/lucide/folder-search-icon";
import { MessageSquareIcon as AnimatedMessageSquare } from "@animateicons/react/lucide/message-square-icon";
import { WorkflowIcon as AnimatedWorkflow } from "@animateicons/react/lucide/workflow-icon";
import { CircleCheckBigIcon as AnimatedCircleCheckBig } from "@animateicons/react/lucide/circle-check-big-icon";
import { LinkIcon as AnimatedLink } from "@animateicons/react/lucide/link-icon";
import { ScissorsIcon as AnimatedScissors } from "@animateicons/react/lucide/scissors-icon";
import { FilePlusIcon as AnimatedFilePlus } from "@animateicons/react/lucide/file-plus-icon";
import { HouseIcon as AnimatedHouse } from "@animateicons/react/lucide/house-icon";
import { RotateCwIcon as AnimatedRotateCw } from "@animateicons/react/lucide/rotate-cw-icon";
import { ZoomOutIcon as AnimatedZoomOut } from "@animateicons/react/lucide/zoom-out-icon";
import { ZoomInIcon as AnimatedZoomIn } from "@animateicons/react/lucide/zoom-in-icon";
import { ShieldAlertIcon as AnimatedShieldAlert } from "@animateicons/react/lucide/shield-alert-icon";
import { GraduationCapIcon as AnimatedGraduationCap } from "@animateicons/react/lucide/graduation-cap-icon";
import { SmartphoneIcon as AnimatedSmartphone } from "@animateicons/react/lucide/smartphone-icon";
import { ListTreeIcon as AnimatedListTree } from "@animateicons/react/lucide/list-tree-icon";
import { CalendarIcon as AnimatedCalendar } from "@animateicons/react/lucide/calendar-icon";
import { ListOrderedIcon as AnimatedListOrdered } from "@animateicons/react/lucide/list-ordered-icon";
import { ShoppingBagIcon as AnimatedShoppingBag } from "@animateicons/react/lucide/shopping-bag-icon";
import { ListPlusIcon as AnimatedListPlus } from "@animateicons/react/lucide/list-plus-icon";
import { GripVerticalIcon as AnimatedGripVertical } from "@animateicons/react/lucide/grip-vertical-icon";
import { ShieldIcon as AnimatedShield } from "@animateicons/react/lucide/shield-icon";
import { PackageXIcon as AnimatedPackageX } from "@animateicons/react/lucide/package-x-icon";
import { PowerIcon as AnimatedPower } from "@animateicons/react/lucide/power-icon";
import { ChartLineIcon as AnimatedChartLine } from "@animateicons/react/lucide/chart-line-icon";
import { LayoutDashboardIcon as AnimatedLayoutDashboard } from "@animateicons/react/lucide/layout-dashboard-icon";
import { WebhookIcon as AnimatedWebhook } from "@animateicons/react/lucide/webhook-icon";
import { UsersRoundIcon as AnimatedUsersRound } from "@animateicons/react/lucide/users-round-icon";
import { QrCodeIcon as AnimatedQrCode } from "@animateicons/react/lucide/qr-code-icon";
import { HardDriveIcon as AnimatedHardDrive } from "@animateicons/react/lucide/hard-drive-icon";
import { LaptopIcon as AnimatedLaptop } from "@animateicons/react/lucide/laptop-icon";
import { PaletteIcon as AnimatedPalette } from "@animateicons/react/lucide/palette-icon";
import { FileCodeIcon as AnimatedFileCode } from "@animateicons/react/lucide/file-code-icon";
import { PackageCheckIcon as AnimatedPackageCheck } from "@animateicons/react/lucide/package-check-icon";
import { BadgeCheckIcon as AnimatedBadgeCheck } from "@animateicons/react/lucide/badge-check-icon";
import { ScrollTextIcon as AnimatedScrollText } from "@animateicons/react/lucide/scroll-text-icon";

const fallbackIcons = new Set([
  "Minimize2",
  "Maximize2",
  "ListEnd",
  "Square",
  "Table2",
  "ListTodo",
  "Volume2",
  "Images",
  "ScanSearch",
  "FolderGit2",
  "FolderOutput",
  "FolderInput",
  "Repeat2",
  "FileInput",
  "Film",
  "CircleArrowDown",
  "PanelRightOpen",
  "PanelRight",
  "Columns2",
  "PanelRightClose",
  "DraftingCompass",
  "FolderKanban",
  "CircleArrowUp",
  "PenLine",
  "SquareTerminal",
  "RefreshCcw",
  "FileBraces",
  "Unplug",
  "FaceSlightlySmiling",
  "Link2Off",
  "Link2",
  "Braces",
  "Container",
]);

const icons: Record<string, typeof AnimatedPlus> = {
  AtSign: AnimatedAtSign,
  User: AnimatedUser,
  Mail: AnimatedMail,
  Ban: AnimatedBan,
  ImagePlus: AnimatedImagePlus,
  BookOpen: AnimatedBookOpen,
  Box: AnimatedBox,
  WifiOff: AnimatedWifiOff,
  CircleCheck: AnimatedCircleCheck,
  Mic: AnimatedMic,
  Languages: AnimatedLanguages,
  MousePointerClick: AnimatedMousePointerClick,
  MessageSquareText: AnimatedMessageSquareText,
  FileScan: AnimatedFileScan,
  Layers: AnimatedLayers,
  KeyRound: AnimatedKeyRound,
  TriangleAlert: AnimatedTriangleAlert,
  Terminal: AnimatedTerminal,
  FolderSearch: AnimatedFolderSearch,
  MessageSquare: AnimatedMessageSquare,
  Workflow: AnimatedWorkflow,
  CircleCheckBig: AnimatedCircleCheckBig,
  Link: AnimatedLink,
  Scissors: AnimatedScissors,
  FilePlus: AnimatedFilePlus,
  House: AnimatedHouse,
  RotateCw: AnimatedRotateCw,
  ZoomOut: AnimatedZoomOut,
  ZoomIn: AnimatedZoomIn,
  ShieldAlert: AnimatedShieldAlert,
  GraduationCap: AnimatedGraduationCap,
  Smartphone: AnimatedSmartphone,
  ListTree: AnimatedListTree,
  Calendar: AnimatedCalendar,
  ListOrdered: AnimatedListOrdered,
  ShoppingBag: AnimatedShoppingBag,
  ListPlus: AnimatedListPlus,
  GripVertical: AnimatedGripVertical,
  Shield: AnimatedShield,
  PackageX: AnimatedPackageX,
  Power: AnimatedPower,
  ChartLine: AnimatedChartLine,
  LayoutDashboard: AnimatedLayoutDashboard,
  Webhook: AnimatedWebhook,
  UsersRound: AnimatedUsersRound,
  QrCode: AnimatedQrCode,
  HardDrive: AnimatedHardDrive,
  Laptop: AnimatedLaptop,
  Palette: AnimatedPalette,
  FileCode: AnimatedFileCode,
  PackageCheck: AnimatedPackageCheck,
  BadgeCheck: AnimatedBadgeCheck,
  ScrollText: AnimatedScrollText,
  PanelLeft: AnimatedPanelLeft,
  CircleHelp: AnimatedHelp,
  Edit2: AnimatedPencil,
  Pen: AnimatedPencil,
  Share2: AnimatedShare,
  Settings2: AnimatedSettings,
  CircleQuestionMark: AnimatedHelp,
  Ellipsis: AnimatedMoreHorizontal,
  Trash: AnimatedTrash2,
  Activity: AnimatedActivity,
  AlertCircle: AnimatedAlertCircle,
  Archive: AnimatedArchive,
  ArrowUpDown: AnimatedArrowUpDown,
  Bot: AnimatedBot,
  ChevronsUpDown: AnimatedChevronsUpDown,
  Clock: AnimatedClock,
  Code: AnimatedCode,
  Code2: AnimatedCode2,
  Coffee: AnimatedCoffee,
  CornerDownRight: AnimatedCornerDownRight,
  CornerRightUp: AnimatedCornerRightUp,
  Cpu: AnimatedCpu,
  Expand: AnimatedExpand,
  EyeOff: AnimatedEyeOff,
  File: AnimatedFile,
  FileArchive: AnimatedFileArchive,
  FolderClosed: AnimatedFolderClosed,
  FolderHeart: AnimatedFolderHeart,
  FolderTree: AnimatedFolderTree,
  GitBranch: AnimatedGitBranch,
  Globe: AnimatedGlobe,
  Hash: AnimatedHash,
  History: AnimatedHistory,
  ImageIcon: AnimatedImageIcon,
  LayoutGrid: AnimatedLayoutGrid,
  Lightbulb: AnimatedLightbulb,
  List: AnimatedList,
  ListChecks: AnimatedListChecks,
  Moon: AnimatedMoon,
  Pause: AnimatedPause,
  Play: AnimatedPlay,
  Save: AnimatedSave,
  Send: AnimatedSend,
  ShieldCheck: AnimatedShieldCheck,
  Shrink: AnimatedShrink,
  Sun: AnimatedSun,
  Tag: AnimatedTag,
  ThumbsDown: AnimatedThumbsDown,
  ThumbsUp: AnimatedThumbsUp,
  Timer: AnimatedTimer,
  ToggleLeft: AnimatedToggleLeft,
  ToggleRight: AnimatedToggleRight,
  Type: AnimatedType,
  UploadCloud: AnimatedUploadCloud,
  Wrench: AnimatedWrench,
  CircleAlert: AnimatedAlertCircle,
  CodeXml: AnimatedCode2,
  RotateCcwClock: AnimatedHistory,
  CloudUpload: AnimatedUploadCloud,
  Funnel: AnimatedFilter,
  Plus: AnimatedPlus,
  Minus: AnimatedMinus,
  Check: AnimatedCheck,
  X: AnimatedX,
  Copy: AnimatedCopy,
  Download: AnimatedDownload,
  Upload: AnimatedUpload,
  ExternalLink: AnimatedExternalLink,
  Search: AnimatedSearch,
  Bell: AnimatedBell,
  Star: AnimatedStar,
  Trash2: AnimatedTrash2,
  Pencil: AnimatedPencil,
  MoreHorizontal: AnimatedMoreHorizontal,
  ChevronDown: AnimatedChevronDown,
  ChevronUp: AnimatedChevronUp,
  ChevronLeft: AnimatedChevronLeft,
  ChevronRight: AnimatedChevronRight,
  ArrowUp: AnimatedArrowUp,
  ArrowDown: AnimatedArrowDown,
  ArrowLeft: AnimatedArrowLeft,
  ArrowRight: AnimatedArrowRight,
  CalendarClock: AnimatedCalendarClock,
  FolderOpen: AnimatedFolderOpen,
  Folder: AnimatedFolder,
  FolderPlus: AnimatedFolderPlus,
  MessageCircle: AnimatedMessageCircle,
  Network: AnimatedNetwork,
  Brain: AnimatedBrain,
  Users: AnimatedUsers,
  UserRound: AnimatedUserRound,
  Sparkles: AnimatedSparkles,
  Server: AnimatedServer,
  Cloud: AnimatedCloud,
  Monitor: AnimatedMonitor,
  Settings: AnimatedSettings,
  Paperclip: AnimatedPaperclip,
  FileText: AnimatedFileText,
  Image: AnimatedImage,
  Video: AnimatedVideo,
  Music: AnimatedMusic,
  Keyboard: AnimatedKeyboard,
  Zap: AnimatedZap,
  Target: AnimatedTarget,
  Pin: AnimatedPin,
  Lock: AnimatedLock,
  RefreshCw: AnimatedRefreshCw,
  RotateCcw: AnimatedRotateCcw,
  SquarePen: AnimatedSquarePen,
  Heart: AnimatedHeart,
  Bookmark: AnimatedBookmark,
  Eye: AnimatedEye,
  Filter: AnimatedFilter,
  SlidersHorizontal: AnimatedSlidersHorizontal,
  LogOut: AnimatedLogOut,
  Menu: AnimatedMenu,
  Info: AnimatedInfo,
  CircleX: AnimatedCircleX,
};

function AnimatedActionIcon({
  Icon,
  props,
  name,
  original,
}: {
  Icon?: typeof AnimatedPlus;
  props: LucideProps;
  name: string;
  original: ReactNode;
}) {
  const host = useRef<HTMLSpanElement>(null);
  const animation = useRef<IconHandle>(null);
  const fallbackAnimation = useRef<Animation | null>(null);
  useEffect(() => {
    // Retain Lucide's SVG class contract for existing styling and selectors.
    host.current
      ?.querySelector("svg")
      ?.classList.add(
        "lucide",
        `lucide-${name.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase()}`,
      );
    const control = host.current?.closest(
      "button, a, [role^='menuitem'], [role='button'], [role='tab'], [role='option'], [role='checkbox'], [role='radio']",
    );
    if (!control) return;
    const start = () => {
      if (
        control.matches(":disabled, [aria-disabled='true']") ||
        window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
      )
        return;
      if (Icon) animation.current?.startAnimation();
      else {
        fallbackAnimation.current?.cancel();
        fallbackAnimation.current =
          host.current
            ?.querySelector("svg")
            ?.animate?.(
              [
                { transform: "scale(1)" },
                { transform: "scale(1.12)" },
                { transform: "scale(1)" },
              ],
              { duration: 350, easing: "ease-out" },
            ) ?? null;
      }
    };
    const stop = () => {
      animation.current?.stopAnimation();
      fallbackAnimation.current?.cancel();
    };
    control.addEventListener("mouseenter", start);
    control.addEventListener("click", start);
    control.addEventListener("focusin", start);
    control.addEventListener("mouseleave", stop);
    control.addEventListener("focusout", stop);
    return () => {
      fallbackAnimation.current?.cancel();
      control.removeEventListener("mouseenter", start);
      control.removeEventListener("click", start);
      control.removeEventListener("focusin", start);
      control.removeEventListener("mouseleave", stop);
      control.removeEventListener("focusout", stop);
    };
  }, [Icon, name]);
  return (
    <span
      ref={host}
      className="contents interactive-action-icon"
      style={{ strokeWidth: props.strokeWidth ?? 2 }}
      aria-hidden="true"
      data-interactive-icon=""
    >
      {Icon ? (
        <Icon
          ref={animation}
          isAnimated={false}
          size={typeof props.size === "number" ? props.size : 24}
          color={props.color}
          className={props.className}
          style={props.style}
          duration={0.7}
        />
      ) : (
        original
      )}
    </span>
  );
}

/** Upgrade action glyphs while retaining custom avatars and state-specific SVGs. */
export function InteractiveIcon({ children }: { children: ReactNode }) {
  return Children.map(children, (child) => {
    if (!isValidElement<LucideProps>(child)) return child;
    const name = (child.type as { displayName?: string }).displayName;
    const Icon = name ? icons[name] : undefined;
    const props = child.props;
    if (
      (!Icon && !fallbackIcons.has(name ?? "")) ||
      props.onClick ||
      props["aria-label"] ||
      props.children ||
      /animate-spin|rotate-|transition-transform/.test(props.className ?? "")
    )
      return child;
    const preserveShape =
      (props.fill && props.fill !== "none") ||
      (props.size !== undefined && typeof props.size !== "number");
    return (
      <AnimatedActionIcon
        Icon={preserveShape ? undefined : Icon}
        props={props}
        name={name!}
        original={child}
      />
    );
  });
}
