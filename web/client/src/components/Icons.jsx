// Chiziqli ikonkalar (24×24). Rangi — currentColor
function Svg({ size = 24, children, fill = 'none', strokeWidth = 2, ...rest }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const SearchIcon = (p) => (
  <Svg {...p} strokeWidth={2.3}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.6-3.6" />
  </Svg>
);

export const BellIcon = (p) => (
  <Svg {...p}>
    <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z" />
    <path d="M10 20.5a2.2 2.2 0 0 0 4 0" />
  </Svg>
);

export const GridIcon = ({ active, ...p }) => (
  <Svg {...p} fill={active ? 'currentColor' : 'none'}>
    <rect x="3.5" y="3.5" width="7" height="7" rx="2" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="2" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="2" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="2" />
  </Svg>
);

export const ProjectsIcon = ({ active, ...p }) => (
  <Svg {...p} fill={active ? 'currentColor' : 'none'}>
    <path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />
  </Svg>
);

export const TrashIcon = (p) => (
  <Svg {...p}>
    <path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5" />
  </Svg>
);

export const ImageIcon = (p) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="3" />
    <circle cx="9" cy="9.5" r="1.8" />
    <path d="m4 18 5-5 4 4 3-3 4 4" />
  </Svg>
);

export const FilterIcon = (p) => (
  <Svg {...p} strokeWidth={2}>
    <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
    <circle cx="15" cy="7" r="2.2" />
    <circle cx="9" cy="17" r="2.2" />
  </Svg>
);

export const SunIcon = (p) => (
  <Svg {...p} strokeWidth={2.2}>
    <circle cx="12" cy="12" r="4.2" />
    <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" />
  </Svg>
);

export const MoonIcon = (p) => (
  <Svg {...p} fill="currentColor" strokeWidth={1.4}>
    <path d="M20.2 14.6A8.4 8.4 0 0 1 9.4 3.8a8.4 8.4 0 1 0 10.8 10.8z" />
  </Svg>
);

export const CrownIcon = (p) => (
  <Svg {...p} fill="currentColor" strokeWidth={1.2}>
    <path d="M3 8.5 7.5 12 12 5l4.5 7L21 8.5 19.2 18H4.8z" />
  </Svg>
);

export const ChevronRight = (p) => (
  <Svg {...p} strokeWidth={2.5}>
    <path d="m9 6 6 6-6 6" />
  </Svg>
);

export const ChevronLeft = (p) => (
  <Svg {...p} strokeWidth={2.5}>
    <path d="m15 6-6 6 6 6" />
  </Svg>
);

export const HomeIcon = ({ active, ...p }) => (
  <Svg {...p} fill={active ? 'currentColor' : 'none'}>
    <path d="M3.5 10.5 12 3.5l8.5 7V20a1 1 0 0 1-1 1h-4.5v-6h-6v6H4.5a1 1 0 0 1-1-1z" />
  </Svg>
);

export const LayersIcon = ({ active, ...p }) => (
  <Svg {...p} fill={active ? 'currentColor' : 'none'}>
    <path d="M12 3 21.5 8 12 13 2.5 8z" />
    <path d="m2.5 12.5 9.5 5 9.5-5" fill="none" />
    <path d="m2.5 16.5 9.5 5 9.5-5" fill="none" />
  </Svg>
);

export const EditIcon = (p) => (
  <Svg {...p}>
    <path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z" />
    <path d="m13.5 6.5 4 4" />
  </Svg>
);

export const BookmarkIcon = ({ active, ...p }) => (
  <Svg {...p} fill={active ? 'currentColor' : 'none'}>
    <path d="M6 3.5h12a1 1 0 0 1 1 1V21l-7-4.5L5 21V4.5a1 1 0 0 1 1-1z" />
  </Svg>
);

export const UserIcon = ({ active, ...p }) => (
  <Svg {...p} fill={active ? 'currentColor' : 'none'}>
    <circle cx="12" cy="8" r="4.2" />
    <path d="M4 21c.8-4.2 4-6.5 8-6.5s7.2 2.3 8 6.5" />
  </Svg>
);

export const PlusIcon = (p) => (
  <Svg {...p} strokeWidth={3}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const DownloadIcon = (p) => (
  <Svg {...p} strokeWidth={2.3}>
    <path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 20h14" />
  </Svg>
);

export const CloseIcon = (p) => (
  <Svg {...p} strokeWidth={2.5}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);

export const CheckIcon = (p) => (
  <Svg {...p} strokeWidth={3}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Svg>
);

export const WalletIcon = (p) => (
  <Svg {...p}>
    <rect x="3" y="6" width="18" height="14" rx="3" />
    <path d="M3 10h18M16 15h2M6 6l9-3 1.5 3" />
  </Svg>
);

export const IdCardIcon = (p) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="3" />
    <circle cx="9" cy="11" r="2.2" />
    <path d="M5.8 16c.6-1.5 1.8-2.3 3.2-2.3s2.6.8 3.2 2.3M14.5 10h4M14.5 13.5h3" />
  </Svg>
);

export const PaletteIcon = (p) => (
  <Svg {...p}>
    <path d="M12 3a9 9 0 1 0 0 18c1.4 0 2-1 2-2 0-1.3-1-1.6-1-3 0-1 .8-2 2-2h2.5a3.5 3.5 0 0 0 3.5-3.5C21 6.6 17 3 12 3z" />
    <circle cx="7.5" cy="11" r="1.2" fill="currentColor" />
    <circle cx="10" cy="7" r="1.2" fill="currentColor" />
    <circle cx="15" cy="7" r="1.2" fill="currentColor" />
  </Svg>
);

export const HelpIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.6M12 17.2v.1" />
  </Svg>
);

export const ChatIcon = (p) => (
  <Svg {...p}>
    <path d="M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4A8 8 0 1 1 20 12z" />
  </Svg>
);

export const SendIcon = (p) => (
  <Svg {...p}>
    <path d="m21 3-9.5 9.5M21 3l-6 18-3.5-8.5L3 9z" />
  </Svg>
);

export const HistoryIcon = (p) => (
  <Svg {...p}>
    <path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1M3.5 4v4h4" />
    <path d="M12 8v4.5l3 2" />
  </Svg>
);

export const SparkIcon = (p) => (
  <Svg {...p} fill="currentColor" strokeWidth={0}>
    <path d="M12 2c.6 4.6 2.4 6.9 7 8-4.6 1.1-6.4 3.4-7 8-.6-4.6-2.4-6.9-7-8 4.6-1.1 6.4-3.4 7-8z" />
  </Svg>
);

export const RefreshIcon = (p) => (
  <Svg {...p}>
    <path d="M20 11a8 8 0 0 0-14.5-4.5M4 4v3.5h3.5M4 13a8 8 0 0 0 14.5 4.5M20 20v-3.5h-3.5" />
  </Svg>
);

export const FolderIcon = (p) => (
  <Svg {...p}>
    <path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />
  </Svg>
);

export const FlameIcon = (p) => (
  <Svg {...p} fill="currentColor" strokeWidth={0}>
    <path d="M12 2c1 3.5 5.5 5.8 5.5 11a5.5 5.5 0 0 1-11 0c0-2.4 1.2-4 2.6-5.2-.1 1.6.5 2.9 1.7 3.4C10.5 8 11.2 5 12 2z" />
  </Svg>
);
