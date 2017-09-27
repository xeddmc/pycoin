import hashlib
import hmac
import unittest

from pycoin.key.BIP32Node import BIP32Node

#################


def crack_secret_exponent_from_k(generator, signed_value, sig, k):
    """
    Given a signature of a signed_value and a known k, return the secret exponent.
    """
    r, s = sig
    return ((s * k - signed_value) * generator.inverse(r)) % generator.order()


def crack_k_from_sigs(generator, sig1, val1, sig2, val2):
    """
    Given two signatures with the same secret exponent and K value, return that K value.
    """

    # s1 = v1 / k1 + (se * r1) / k1
    # s2 = v2 / k2 + (se * r2) / k2
    # and k = k1 = k2
    # so
    # k * s1 = v1 + (se * r1)
    # k * s2 = v2 + (se * r2)
    # so
    # k * s1 * r2 = r2 * v1 + (se * r1 * r2)
    # k * s2 * r1 = r1 * v2 + (se * r2 * r1)
    # so
    # k (s1 * r2 - s2 * r1) = r2 * v1 - r1 * v2
    # so
    # k = (r2 * v1 - r1 * v2) / (s1 * r2 - s2 * r1)

    r1, s1 = sig1
    r2, s2 = sig2
    if r1 != r2:
        raise ValueError("r values of signature do not match")
    k = (r2 * val1 - r1 * val2) * generator.inverse(r2 * s1 - r1 * s2)
    return k % generator.order()


from pycoin.ecdsa.secp256k1 import secp256k1_generator


def make_gen_k_const(K):

    def gen_k(*args):
        return K
    return gen_k


class CrackSigTest(unittest.TestCase):
    def test_crack_secret_exponent_from_k(self):
        k = 105
        se = 181919191
        gen_k = make_gen_k_const(k)
        val = 488819181819384
        sig = secp256k1_generator.sign(se, val, gen_k=gen_k)
        cracked_se = crack_secret_exponent_from_k(secp256k1_generator, val, sig, k)
        self.assertEqual(cracked_se, se)

    def test_crack_k_from_sigs(self):
        k = 105
        se = 181919191
        gen_k = make_gen_k_const(k)
        val1 = 488819181819384
        val2 = 588819181819384
        sig1 = secp256k1_generator.sign(se, val1, gen_k=gen_k)
        sig2 = secp256k1_generator.sign(se, val2, gen_k=gen_k)
        cracked_k = crack_k_from_sigs(secp256k1_generator, sig1, val1, sig2, val2)
        self.assertEqual(cracked_k, k)


import struct

from pycoin.ecdsa.secp256k1 import secp256k1_generator
from pycoin.encoding import public_pair_to_sec, from_bytes_32, to_bytes_32
from pycoin.key.BIP32Node import BIP32Node


ORDER = secp256k1_generator.order()


def ascend_bip32(bip32_pub_node, secret_exponent, child):
    """
    Given a BIP32Node with public derivation child "child" with a known private key,
    return the secret exponent for the bip32_pub_node.
    """
    i_as_bytes = struct.pack(">l", child)
    sec = public_pair_to_sec(bip32_pub_node.public_pair(), compressed=True)
    data = sec + i_as_bytes
    I64 = hmac.HMAC(key=bip32_pub_node._chain_code, msg=data, digestmod=hashlib.sha512).digest()
    I_left_as_exponent = from_bytes_32(I64[:32])
    return (secret_exponent - I_left_as_exponent) % ORDER


def crack_bip32(bip32_pub_node, secret_exponent, path):
    paths = path.split("/")
    while len(paths):
        path = int(paths.pop())
        secret_exponent = ascend_bip32(bip32_pub_node.subkey_for_path("/".join(paths)), secret_exponent, path)
    return BIP32Node(bip32_pub_node._netcode, bip32_pub_node._chain_code, bip32_pub_node._depth,
                     bip32_pub_node._parent_fingerprint, bip32_pub_node._child_index, secret_exponent=secret_exponent)


class CrackBIP32Test(unittest.TestCase):
    def test_crack_bip32(self):
        bip32key = BIP32Node.from_master_secret(b"foo")
        bip32_pub = bip32key.public_copy()
        secret_exponent_p0_1_7_9 = bip32key.subkey_for_path("0/1/7/9").secret_exponent()
        cracked_bip32_node = crack_bip32(bip32_pub, secret_exponent_p0_1_7_9, "0/1/7/9")
        self.assertEqual(cracked_bip32_node.hwif(as_private=True), bip32key.hwif(as_private=True))

    def test_ascend_bip32(self):
        bip32key = BIP32Node.from_master_secret(b"foo")
        bip32_pub = bip32key.public_copy()
        secret_exponent_p9 = bip32key.subkey_for_path("9").secret_exponent()
        secret_exponent = ascend_bip32(bip32_pub, secret_exponent_p9, 9)
        self.assertEqual(secret_exponent, bip32key.secret_exponent())
