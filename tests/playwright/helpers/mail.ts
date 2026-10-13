import nodemailer from 'nodemailer';
import { ImapFlow } from 'imapflow';
import { simpleParser, ParsedMail } from 'mailparser';

// A real test mailbox (IMAP to read, SMTP to send), configured through env:
// MAIL_<KEY>_ADDRESS, _IMAP_HOST, _IMAP_PORT, _SMTP_HOST, _SMTP_PORT, _USER, _PASSWORD.
export type MailboxKey = 'SUPPORT' | 'CUSTOMER' | 'CUSTOMER2';

export type Mailbox = {
  address: string;
  imap: { host: string; port: number };
  smtp: { host: string; port: number };
  user: string;
  password: string;
};

export function mailbox(key: MailboxKey): Mailbox {
  const read = (name: string) => {
    const value = process.env[`MAIL_${key}_${name}`];
    if (!value) throw new Error(`MAIL_${key}_${name} is not set (see tests/playwright/.env.example)`);
    return value;
  };
  return {
    address: read('ADDRESS'),
    imap: { host: read('IMAP_HOST'), port: Number(read('IMAP_PORT')) },
    smtp: { host: read('SMTP_HOST'), port: Number(read('SMTP_PORT')) },
    user: read('USER'),
    password: read('PASSWORD'),
  };
}

export async function sendMail(
  from: Mailbox,
  mail: { to: string; subject: string; text: string; cc?: string[]; inReplyTo?: string; references?: string[] }
) {
  const transport = nodemailer.createTransport({
    host: from.smtp.host,
    port: from.smtp.port,
    secure: from.smtp.port === 465,
    auth: { user: from.user, pass: from.password },
  });
  const info = await transport.sendMail({ from: from.address, ...mail });
  transport.close();
  return info.messageId as string;
}

// Polls the mailbox INBOX until a message received after `since` matches `predicate`.
export async function waitForMail(
  box: Mailbox,
  predicate: (mail: ParsedMail) => boolean,
  { since, timeoutMs = 180_000, intervalMs = 10_000 }: { since: Date; timeoutMs?: number; intervalMs?: number }
): Promise<ParsedMail> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const client = new ImapFlow({
      host: box.imap.host,
      port: box.imap.port,
      secure: box.imap.port === 993,
      auth: { user: box.user, pass: box.password },
      logger: false,
    });
    await client.connect();
    const lock = await client.getMailboxLock('INBOX');
    try {
      const uids = (await client.search({ since }, { uid: true })) || [];
      for (const uid of uids.reverse()) {
        const msg = await client.fetchOne(String(uid), { source: true }, { uid: true });
        if (!msg || !msg.source) continue;
        const parsed = await simpleParser(msg.source);
        if (parsed.date && parsed.date < since) continue;
        if (predicate(parsed)) return parsed;
      }
    } finally {
      lock.release();
      await client.logout();
    }
    await new Promise(r => setTimeout(r, intervalMs));
  }
  throw new Error(`no matching mail in ${box.address} within ${timeoutMs}ms`);
}
