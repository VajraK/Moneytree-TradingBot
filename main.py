from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityUrl, MessageEntityTextUrl
import re
from web3 import Web3
from eth_account import Account
import json
import configparser
import datetime
import requests
import time

# Read configuration file
config = configparser.ConfigParser()
config.read('config.ini')

# Load config variables
uniswap_factory_addr = config.get('uniswap', 'factory')
uniswap_factory_address = Web3.to_checksum_address(uniswap_factory_addr)
etherscan_api_key = config.get('etherscan', 'api')
etherscan_url = config.get('etherscan', 'url')
api_id = int(config.get('telegram', 'api_id'))
api_hash = config.get('telegram', 'api_hash')
phone_number = config.get('telegram', 'phone_number')
channel_username = config.get('telegram', 'channel_username')
infura_url = config.get('web3', 'infura_url')
web3 = Web3(Web3.HTTPProvider(infura_url))  # Connecting to Infura
private_key = config.get('wallet', 'private_key')
account = Account.from_key(private_key)
public_key = config.get('wallet', 'public_key')
recipient_address = Web3.to_checksum_address(public_key)
amount_of_ether = float(config.get('ether', 'amount_of_ether'))
eth_amount = web3.to_wei(amount_of_ether, 'ether')
weth_address = config.get('ether', 'weth_address')
weth_ad = Web3.to_checksum_address(weth_address)
min_to_receive = int(config.get('ether', 'min_to_receive'))
min_tokens = min_to_receive
timex = int(config.get('details', 'time'))
deadline = int(datetime.datetime.now().timestamp()) + (timex * 60)


# Load the Uniswap V2 Router Contract ABI
with open('IUniswapV2Router02.json') as file:
    file_data = json.load(file)
    uniswap_v2_router_abi = file_data["abi"]
uniswap_v2_router_address = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'
uniswap_v2_router_address_checksummed = Web3.to_checksum_address(uniswap_v2_router_address)
uniswap_v2_router_contract = web3.eth.contract(address=uniswap_v2_router_address_checksummed, abi=uniswap_v2_router_abi)
# Load the Uniswap V2 Pair Contract ABI
with open('IUniswapV2Pair.json') as file:
    file_data = json.load(file)
    uniswap_v2_pair_abi = file_data["abi"]
# Load the Uniswap V2 ERC20 Contract ABI
with open('IUniswapV2ERC20.json') as file:
    file_data = json.load(file)
    uniswap_v2_erc20_abi = file_data["abi"]
# Simplified ABI for Uniswap Factory contract focusing on getPair function
uniswap_factory_abi = json.loads('[{"constant":true,"inputs":[{"internalType":"address","name":"","type":"address"},'
                                 '{"internalType":"address","name":"","type":"address"}],"name":"getPair","outputs":'
                                 '[{"internalType":"address","name":"","type":"address"}],"payable":false,'
                                 '"stateMutability":"view","type":"function"}]')
# Initialize the Uniswap Factory contract
factory_contract = web3.eth.contract(address=uniswap_factory_address, abi=uniswap_factory_abi)


# Get transaction details
def get_transaction_details(ether_url, txn_hash, api_key):
    url = f"https://{ether_url}/api?module=proxy&action=eth_getTransactionByHash&txhash={txn_hash}&apikey={api_key}"
    response = requests.get(url)
    return response.json()


# Getting token price
def get_current_token_price(token_contract_address, pair_contract):
    reserves = pair_contract.functions.getReserves().call()
    reserve_token = reserves[0] if token_contract_address.lower() < weth_ad.lower() else reserves[1]
    reserve_weth = reserves[1] if token_contract_address.lower() < weth_ad.lower() else reserves[0]
    price_of_token_in_weth = reserve_weth / reserve_token
    return price_of_token_in_weth


# Uniswap approval to spend token
def approve_token(token_contract_address, spender_address, amount_to_approve):
    token_contract = web3.eth.contract(address=token_contract_address, abi=uniswap_v2_erc20_abi)
    approve_txn = token_contract.functions.approve(spender_address, amount_to_approve).build_transaction({
        'from': recipient_address,
        'gas': 100000,
        'gasPrice': web3.eth.gas_price,
        'nonce': web3.eth.get_transaction_count(recipient_address),
    })
    signed_txn = web3.eth.account.sign_transaction(approve_txn, private_key=private_key)
    txn_receipt = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
    return web3.to_hex(txn_receipt)


# Fetch token balance
def get_token_balance(token_contract_address, account_address):
    token_contract = web3.eth.contract(address=token_contract_address, abi=uniswap_v2_erc20_abi)
    balance = token_contract.functions.balanceOf(account_address).call()
    return balance


def sell_token(token_contract_address, amount_to_sell, min_eth_to_receive, deadl):
    swap_path = [token_contract_address, weth_ad]
    sell_txn = uniswap_v2_router_contract.functions.swapExactTokensForETH(
        amount_to_sell,
        min_eth_to_receive,
        swap_path,
        recipient_address,
        deadl
    ).build_transaction({
        'from': recipient_address,
        'gas': 200000,  # Adjust gas according to needs
        'gasPrice': web3.eth.gas_price,
        'nonce': web3.eth.get_transaction_count(recipient_address, 'pending'),
    })
    signed_txn = web3.eth.account.sign_transaction(sell_txn, private_key=private_key)
    txn_receipt = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
    return web3.to_hex(txn_receipt)


# Connection to Telegram
client = TelegramClient('session_name', api_id, api_hash)


# The Event
@client.on(events.NewMessage(chats=channel_username))
async def my_event_handler(event):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print("\n" * 2 + "------------------------------" + "\n" + f"Timestamp: {timestamp}\n" + "\n" + event.raw_text)

    if hasattr(event.message, 'entities') and event.message.entities:
        for entity in event.message.entities:
            if isinstance(entity, (MessageEntityUrl, MessageEntityTextUrl)):
                url = event.message.text[entity.offset:entity.offset + entity.length] if isinstance(entity,
                                                                                                    MessageEntityUrl) \
                    else entity.url
                if "etherscan.io/token/" in url:
                    print(f"URL found: {url}")

                    match = re.search(r'https://etherscan.io/token/([0-9a-zA-Z]{42})', url)
                    if match:
                        token_contract_address = match.group(1)
                        print(f"Token Contract Address: {token_contract_address}")

                        token_contract_address_checked = Web3.to_checksum_address(token_contract_address)
                        swap_path = [weth_ad, token_contract_address_checked]

                        txn = uniswap_v2_router_contract.functions.swapExactETHForTokens(
                            min_tokens,
                            swap_path,
                            recipient_address,
                            deadline
                        ).build_transaction({
                            'from': recipient_address,
                            'value': eth_amount,
                            'gas': 200000,
                            'gasPrice': web3.eth.gas_price,
                            'nonce': web3.eth.get_transaction_count(recipient_address),
                        })

                        signed_txn = web3.eth.account.sign_transaction(txn, private_key=private_key)
                        txn_receipt = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
                        txn_hash = web3.to_hex(txn_receipt)
                        print(f"TRANSACTION SUBMITTED. Hash: {txn_hash}")

                        # Get transaction details
                        transaction_details = get_transaction_details(etherscan_url, txn_hash, etherscan_api_key)
                        print(f"Transactions details: {transaction_details}")

                        # Get token price at time of Buy
                        pair_address = (factory_contract.functions.getPair(token_contract_address_checked, weth_ad).
                                        call())
                        if pair_address != "0x0000000000000000000000000000000000000000":
                            print(f"Pair address: {pair_address}")
                        else:
                            print("Pair does not exist.")
                        pair_contract = web3.eth.contract(address=pair_address, abi=uniswap_v2_pair_abi)
                        buy_price = get_current_token_price(token_contract_address_checked, pair_contract)
                        print(f"Buy price of token in WETH: {buy_price}")

                        # Waiting for 1.5x or 0.95x
                        print("Waiting for 1.5x or 0.95x!")
                        while True:
                            current_price = get_current_token_price(token_contract_address_checked, pair_contract)
                            if current_price >= 1.5 * buy_price or current_price <= 0.95 * buy_price:
                                print("Condition met for selling the token.")
                                token_balance_to_sell = get_token_balance(token_contract_address_checked,
                                                                          recipient_address)
                                print(f"Token balance to sell: {token_balance_to_sell}")
                                print("Approving Uniswap router to spend tokens...")
                                approve_token(token_contract_address_checked, uniswap_v2_router_address,
                                              token_balance_to_sell)
                                print("Selling tokens...")
                                min_eth_to_receive = 0
                                sell_txn_hash = sell_token(token_contract_address_checked, token_balance_to_sell,
                                                           min_eth_to_receive, deadline)
                                print(f"Sell transaction submitted. Hash: {sell_txn_hash}")
                                break
                            time.sleep(5)


def main():
    client.start(phone=lambda: phone_number)
    print("Userbot is running and monitoring the channel...")
    client.run_until_disconnected()


if __name__ == '__main__':
    main()
