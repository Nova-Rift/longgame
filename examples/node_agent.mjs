// Play Long Game from JavaScript (or any language) through the JSON-lines protocol.
//   node examples/node_agent.mjs
// Starts `longgame serve`, presses random keys until the lifetime is over, and prints the scorecard. Needs the
// `longgame` command on your PATH (activate the virtualenv you installed it in), or set LONGGAME to its full path.
import {spawn} from 'node:child_process'
import {createInterface} from 'node:readline'

const game = spawn(process.env.LONGGAME ?? 'longgame', ['serve'], {stdio: ['pipe', 'pipe', 'inherit']})
const replies = createInterface({input: game.stdout})[Symbol.asyncIterator]()
async function send(message) {
  game.stdin.write(JSON.stringify(message) + '\n')
  const {value} = await replies.next()
  const reply = JSON.parse(value)
  if (reply.error) throw new Error(reply.error)
  return reply
}

let {observation: obs} = await send({cmd: 'reset'})
while (!obs.done) {
  const choices = obs.available_actions.filter((a) => a !== 0)   // never restart (0)
  ;({observation: obs} = await send({cmd: 'step', action: choices[Math.floor(Math.random() * choices.length)]}))
  if (obs.result) console.log(`world ${obs.result.world} level ${obs.result.level + 1}: ${obs.result.cleared ? 'finished' : 'out of actions'}`)
}
const {scorecard} = await send({cmd: 'score'})
console.log('overall', scorecard.overall, scorecard.phases)
game.stdin.end()
