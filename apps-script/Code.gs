/**
 * 论文雷达 · 每日摘要邮件（Google Apps Script）
 * 每小时运行一次 sendDigest()：工作日 09:30–13:00（北京时间）读取网站上的 digest/latest.json，
 * 若是今天的摘要且还没发过，就用你自己的 Gmail 发出，然后记下它的 id，保证一天只发一封。
 */
const DIGEST_URL = 'https://ctao7271-a11y.github.io/paper-radar/digest/latest.json';
const TO = '';  // 收件人邮箱（粘贴后填写）
const TEST_TO = '';  // 你自己的邮箱，testSend() 只发给它
const TZ = 'Asia/Shanghai';
const SENDER_NAME = '论文雷达';

/** 定时触发：满足条件才发送 */
function sendDigest() {
  const now = new Date();
  const weekday = Number(Utilities.formatDate(now, TZ, 'u'));   // 1=周一 … 7=周日
  const hm = Utilities.formatDate(now, TZ, 'HH:mm');
  if (weekday > 5 || hm < '09:30' || hm > '13:00') return;
  const d = fetchDigest_();
  if (!d) return;
  const today = Utilities.formatDate(now, TZ, 'yyyy-MM-dd');
  const props = PropertiesService.getScriptProperties();
  if (d.date !== today || !d.count || d.id === props.getProperty('lastSentId')) return;
  MailApp.sendEmail(TO, d.subject, d.text, { htmlBody: d.html, name: SENDER_NAME });
  props.setProperty('lastSentId', d.id);
  console.log('已发送 ' + d.id + '：' + d.subject);
}

/** 测试：把网站上当前的摘要只发给自己（不影响正式发送记录） */
function testSend() {
  const d = fetchDigest_();
  if (!d) throw new Error('读取摘要失败，见执行日志');
  MailApp.sendEmail(TEST_TO, '[测试] ' + d.subject, d.text, { htmlBody: d.html, name: SENDER_NAME });
  console.log('测试邮件已发到 ' + TEST_TO + '（摘要日期 ' + d.date + '）');
}

/** 只需运行一次：建立“每小时一次”的定时触发器（先删旧的） */
function setup() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'sendDigest')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('sendDigest').timeBased().everyHours(1).create();
  // 网站上当前这份摘要视为已发送，避免安装当天重复发
  const d = fetchDigest_();
  if (d) PropertiesService.getScriptProperties().setProperty('lastSentId', d.id);
  console.log('已设置：工作日 09:30–13:00 每小时检查一次。当前摘要 ' + (d ? d.id : '（无）') + ' 视为已发送。');
}

function fetchDigest_() {
  const res = UrlFetchApp.fetch(DIGEST_URL + '?t=' + Date.now(), { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    console.warn('读取失败 HTTP ' + res.getResponseCode());
    return null;
  }
  try {
    return JSON.parse(res.getContentText('UTF-8'));
  } catch (e) {
    console.warn('JSON 解析失败：' + e);
    return null;
  }
}
