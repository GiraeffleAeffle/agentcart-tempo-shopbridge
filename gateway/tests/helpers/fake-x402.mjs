import { createHash } from 'node:crypto';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { X402_ASSET, X402_NETWORK, AUTHORIZATION_USED_TOPIC } from '../../scripts/verifier-x402.mjs';
export const PAYER = '0x1111111111111111111111111111111111111111';
export const PAY_TO = '0x2222222222222222222222222222222222222222';
export const TX = `0x${'ab'.repeat(32)}`;
export const NONCE = '0x68d8b9f6ce3e20691028d2c78b6904e615d34346820c101f4168c4f5a44c74d2';
const pad = v => `0x${v.slice(2).padStart(64,'0')}`;
// uniqueTransactions mirrors a real facilitator (one tx hash per authorization);
// the default fixed TX lets tests exercise transaction-hash replay conflicts.
export async function fakeX402({ facilitatorPort = 0, rpcPort = 0, uniqueTransactions = false, derivePayer = false } = {}) {
  const state = { calls: [], rpcCalls: [], rpcRequests: [], latestBlock: 101, settlementBlock: 101, rpcError: null, callsDelay: {}, invalid: false, ambiguous: false, unresolved: false, missingTransfer: false, wrongAmount: false, redirect: false, settled: false, transaction: TX, authorization: null, requirements: null };
  state.unsupported = false;
  state.blockTimestamp = Math.floor(Date.now() / 1000);
  state.authorizationStateOverrides = {};
  const payer = () => derivePayer ? state.authorization?.from || PAYER : PAYER;
  function logs() {
    const a = state.authorization || {from:PAYER,to:PAY_TO,nonce:NONCE,value:'1000000'};
    const base = {address:X402_ASSET,blockNumber:`0x${state.settlementBlock.toString(16)}`,blockHash:`0x${'01'.repeat(32)}`,transactionHash:state.transaction,transactionIndex:'0x0',removed:false};
    return [ ...(state.missingTransfer ? [] : [{...base, logIndex:'0x0', topics:['0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',pad(a.from),pad(a.to)], data:pad(`0x${(BigInt(a.value)+(state.wrongAmount?1n:0n)).toString(16)}`)}]),
      ...(state.missingAuthorization ? [] : [{...base,logIndex:'0x1',topics:[AUTHORIZATION_USED_TOPIC,pad(a.from),a.nonce],data:'0x'}]) ];
  }
  async function input(req) { let body=''; for await (const chunk of req) body+=chunk; return body ? JSON.parse(body) : {}; }
  const facilitator = http.createServer(async(req,res) => {
    state.calls.push(req.url); if(state.redirect) {res.writeHead(302,{location:'http://127.0.0.1:1/'});res.end();return;}
    const body=await input(req); if(body.paymentPayload) {state.authorization=body.paymentPayload.payload.authorization;state.requirements=body.paymentRequirements;if(uniqueTransactions) state.transaction=`0x${createHash('sha256').update(String(state.authorization.nonce)).digest('hex')}`;}
    if (state.callsDelay[req.url]) await new Promise(resolve => setTimeout(resolve, state.callsDelay[req.url]));
    res.setHeader('content-type','application/json');
    if(req.url==='/supported') res.end(JSON.stringify({kinds: state.unsupported ? [] : [{x402Version:2,scheme:'exact',network:X402_NETWORK}]}));
    else if(req.url==='/verify') res.end(JSON.stringify({isValid:!state.invalid,payer:payer()}));
    else if(req.url==='/settle') {state.settled=!state.unresolved;if(state.ambiguous) {res.writeHead(503);res.end('{}');} else res.end(JSON.stringify({success:true,transaction:state.transaction,network:X402_NETWORK,payer:payer()}));}
    else {res.writeHead(404);res.end('{}');}
  });
  const rpc = http.createServer(async(req,res) => {
    const body=await input(req);
    state.rpcCalls.push(body.method);
    state.rpcRequests.push(body);
    let result;
    if (state.rpcError) {
      res.end(JSON.stringify({jsonrpc:'2.0',id:body.id,error:state.rpcError}));
      return;
    }
    if(body.method==='eth_blockNumber') result=`0x${state.latestBlock.toString(16)}`;
    else if(body.method==='eth_call') {
      const block = body.params[1];
      const used = state.authorizationStateOverrides[block]
        ?? (state.settled && (block === 'latest' || BigInt(block) >= BigInt(state.settlementBlock)));
      result=pad(used?'0x1':'0x0');
    }
    else if(body.method==='eth_getBlockByNumber') {
      const number = body.params[0] === 'latest' ? state.latestBlock : Number(BigInt(body.params[0]));
      result = {
        number: `0x${number.toString(16)}`,
        timestamp: `0x${(state.blockTimestamp - (state.latestBlock - number) * 2).toString(16)}`,
        hash: `0x${'01'.repeat(32)}`, parentHash: `0x${'02'.repeat(32)}`, transactions: [],
      };
    }
    else if(body.method==='eth_getLogs') {
      const filter = body.params[0];
      result=state.settled ? logs().filter(l=>l.topics[0]===AUTHORIZATION_USED_TOPIC && BigInt(l.blockNumber)>=BigInt(filter.fromBlock) && BigInt(l.blockNumber)<=BigInt(filter.toBlock)) : [];
    }
    else if(body.method==='eth_getTransactionReceipt') result=state.settled ? {transactionHash:state.transaction,transactionIndex:'0x0',blockHash:`0x${'01'.repeat(32)}`,blockNumber:`0x${state.settlementBlock.toString(16)}`,from:payer(),to:X402_ASSET,cumulativeGasUsed:'0x5208',gasUsed:'0x5208',effectiveGasPrice:'0x1',contractAddress:null,logs:logs(),logsBloom:`0x${'00'.repeat(256)}`,status:'0x1',type:'0x2'} : null;
    else {res.end(JSON.stringify({jsonrpc:'2.0',id:body.id,error:{code:-32601,message:'unknown method'}}));return;}
    res.setHeader('content-type','application/json');res.end(JSON.stringify({jsonrpc:'2.0',id:body.id,result}));
  });
  await Promise.all([new Promise(r=>facilitator.listen(facilitatorPort,'127.0.0.1',r)),new Promise(r=>rpc.listen(rpcPort,'127.0.0.1',r))]);
  return { state, facilitator:`http://127.0.0.1:${facilitator.address().port}`, rpc:`http://127.0.0.1:${rpc.address().port}`, close:()=>Promise.all([new Promise(r=>facilitator.close(r)),new Promise(r=>rpc.close(r))]) };
}
if(import.meta.url===pathToFileURL(process.argv[1]||'').href) {
  const fake=await fakeX402({facilitatorPort:Number(process.env.FAKE_X402_FACILITATOR_PORT||4291),rpcPort:Number(process.env.FAKE_X402_RPC_PORT||4292),uniqueTransactions:true,derivePayer:true});
  console.log(JSON.stringify({facilitator:fake.facilitator,rpc:fake.rpc}));
  for(const signal of ['SIGTERM','SIGINT']) process.on(signal,async()=>{await fake.close();process.exit(0);});
}
