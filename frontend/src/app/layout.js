import './globals.css';

export const metadata = {
  title: 'Ohabai Pipeline',
  description: 'Omnichannel inbox',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
