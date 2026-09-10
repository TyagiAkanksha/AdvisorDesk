import { ImageResponse } from 'next/og';

export const size = { width: 32, height: 32 };
export const contentType = 'image/png';

// phase-8 task-07 (DESIGN.md §A4): generated favicon — navy rounded square, white "A" (sans —
// Satori ignores fontFamily without an embedded font; fine at 32px). No binary asset to
// maintain; the create-next-app favicon.ico was deleted in the same commit.
export default function Icon() {
  return new ImageResponse(
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#1E3A5F',
        borderRadius: 7,
        color: '#FFFFFF',
        fontSize: 22,
        fontWeight: 700,
      }}
    >
      A
    </div>,
    size,
  );
}
